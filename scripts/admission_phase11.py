"""Lightweight automatic search for a steady background-CPU window."""
from __future__ import annotations
import ctypes as C
import json
import os
import statistics
import time

from ffv2.darwin import libraries


def ticks():
    system,_=libraries();host=system.mach_host_self()
    processors=C.c_uint32();count=C.c_uint32();data=C.POINTER(C.c_int)()
    system.host_processor_info.argtypes=[C.c_uint32,C.c_int,C.POINTER(C.c_uint32),C.POINTER(C.POINTER(C.c_int)),C.POINTER(C.c_uint32)]
    system.host_processor_info.restype=C.c_int
    system.mach_vm_deallocate.argtypes=[C.c_uint32,C.c_uint64,C.c_uint64]
    system.mach_vm_deallocate.restype=C.c_int
    task=C.c_uint32.in_dll(system,'mach_task_self_').value
    try:
        if system.host_processor_info(host,2,C.byref(processors),C.byref(data),C.byref(count)):
            raise RuntimeError('Per-core CPU information unavailable')
        if not 1<=processors.value<=64 or count.value!=processors.value*4:raise RuntimeError('Unexpected processor table')
        values=[sum(data[j*4+i]&0xffffffff for j in range(processors.value)) for i in range(4)]
        return {'at':time.monotonic(),'ticks':values,'processors':processors.value}
    finally:
        if data:system.mach_vm_deallocate(task,C.cast(data,C.c_void_p).value,count.value*C.sizeof(C.c_int))
        system.mach_port_deallocate(task,host)


def window_valid(samples,*,maximum=14.5,span=.75,required=8):
    if len(samples)<required:return False
    recent=samples[-required:]
    return all(abs(s['capacity']-s['processors'])<=.5 for s in recent) and max(s['busy'] for s in recent)<=maximum and max(s['busy'] for s in recent)-min(s['busy'] for s in recent)<=span


def readiness(samples,elapsed,*,required=8,probe_after=15,maximum=6.0):
    if window_valid(samples,required=required,maximum=maximum):return 'stable_preflight'
    if elapsed>=probe_after and len(samples)>=required:
        recent=samples[-required:]
        if all(abs(s['capacity']-s['processors'])<=.5 and -.15<=s['busy']<=maximum for s in recent):
            return 'exploratory_block'
    return None


def wait_window(path,identity,*,timeout,required=8,probe_after=15,check=None,admit=None):
    start=time.monotonic();before=ticks();samples=[];last_notice=start
    with path.open('a') as stream:
        while time.monotonic()-start<timeout:
            time.sleep(1)
            if check:check()
            after=ticks();elapsed=after['at']-before['at']
            delta=[(b-a)&0xffffffff for a,b in zip(before['ticks'],after['ticks'])]
            sample={'identity':identity,'elapsed':time.monotonic()-start,'processors':after['processors'],
                    'busy':sum(delta[i] for i in (0,1,3))/os.sysconf('SC_CLK_TCK')/elapsed,
                    'capacity':sum(delta)/os.sysconf('SC_CLK_TCK')/elapsed}
            resource=admit() if admit else {'ready':True,'reasons':[]}
            sample['resource_admission']=resource
            samples.append(sample);stream.write(json.dumps(sample)+'\n');stream.flush();before=after
            state=readiness(samples,time.monotonic()-start,required=required,probe_after=probe_after)
            if state and resource['ready']:
                return {'wait_seconds':time.monotonic()-start,'classification':state,'samples':samples[-required:],
                        'acceptance_basis':'Observed complete-block conditions only; readiness is not speed or stability acceptance.'}
            if time.monotonic()-last_notice>=30:
                print(json.dumps({'waiting_for_stable_cpu':identity,'wait_seconds':round(time.monotonic()-start),
                    'recent_busy_cores':[round(s['busy'],2) for s in samples[-required:]],'resource_reasons':resource['reasons']}),flush=True);last_notice=time.monotonic()
    raise RuntimeError('Automatic stable-window admission budget exhausted')
