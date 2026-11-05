#!/usr/bin/python3 -B
"""Owned CPU-load replay and excluded worker profiling with frozen media argv."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import random
import statistics
import struct
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase10')))
sys.path.insert(0,str(ROOT))
from ffv2.darwin import libraries
from ffv2.io import sha256_file,write_json


def read(path):return json.loads(Path(path).read_text())


def host_ticks():
    system,_=libraries();host=system.mach_host_self()
    values=(C.c_uint32*4)();count=C.c_uint32(4)
    system.host_statistics.argtypes=[C.c_uint32,C.c_int,C.c_void_p,C.POINTER(C.c_uint32)]
    system.host_statistics.restype=C.c_int
    try:
        if system.host_statistics(host,3,C.byref(values),C.byref(count)) or count.value!=4:
            raise RuntimeError('Host CPU counters unavailable')
        return list(values)
    finally:system.mach_port_deallocate(C.c_uint32.in_dll(system,'mach_task_self_').value,host)


def cpu_usage(pid):
    _,proc=libraries();buffer=C.create_string_buffer(4096)
    if proc.proc_pid_rusage(pid,2,C.byref(buffer)):raise RuntimeError('Owned load worker usage unavailable')
    return sum(struct.unpack_from('QQ',buffer.raw,16))


def validate_child_request(request):
    if type(request.get('load_workers')) is not int or request['load_workers'] not in (0,2):
        raise ValueError('Only zero or two owned load workers are allowed')
    if type(request.get('profiled')) is not bool:
        raise ValueError('Explicit diagnostic observer state required')
    if not isinstance(request.get('argv'),list) or not all(isinstance(a,str) for a in request['argv']):
        raise ValueError('Encoding arguments must be strings')
    for key in ('binary','output','load_binary','load_prefix','child_report'):
        if not isinstance(request.get(key),str) or not Path(request[key]).is_absolute():
            raise ValueError('Absolute trusted task path required: '+key)
    if request['profiled']:
        for key in ('observer','trace'):
            if not isinstance(request.get(key),str) or not Path(request[key]).is_absolute():
                raise ValueError('Absolute observer path required: '+key)


def child(path):
    request=read(path);validate_child_request(request);loads=[];details=[]
    try:
        for index in range(request['load_workers']):
            output=Path(request['load_prefix']+str(index)+'.json')
            process=subprocess.Popen([request['load_binary'],'50','1150',str(os.getpid()),str(output)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            loads.append((process,output))
        time.sleep(.25)
        before=host_ticks();load_before={p.pid:cpu_usage(p.pid) for p,_ in loads}
        command=['/usr/bin/time','-lp']
        if request['profiled']:
            command+=['/usr/bin/env','DYLD_INSERT_LIBRARIES='+request['observer'],'FFV2_WORKER_TRACE='+request['trace']]
        command += [request['binary'],*request['argv'],request['output']]
        started=time.monotonic()
        completed=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=1100)
        elapsed=time.monotonic()-started
        after=host_ticks();load_after={p.pid:cpu_usage(p.pid) for p,_ in loads}
        sys.stdout.buffer.write(completed.stdout);sys.stdout.flush()
        sys.stderr.buffer.write(completed.stderr);sys.stderr.flush()
        for process,output in loads:
            process.terminate();_,stderr=process.communicate(timeout=5)
            if process.returncode or not output.is_file():raise RuntimeError('Owned load worker failed: '+stderr.decode()[-500:])
            record=read(output);record['window_cpu_mach']=load_after[process.pid]-load_before[process.pid];details.append(record)
        ticks=[(b-a)&0xffffffff for a,b in zip(before,after)]
        write_json(Path(request['child_report']),{'status':'completed' if completed.returncode==0 else 'failed',
            'encoding_wall_seconds':elapsed,'encoding_argv':command,'exit_code':completed.returncode,
            'load_workers':details,'host_cpu_ticks':ticks,'host_clock_ticks':os.sysconf('SC_CLK_TCK'),
            'logical_cpus':os.cpu_count(),'system_memory_waiver':os.environ.get('FFV2_IGNORE_SYSTEM_MEMORY')=='1'})
        return completed.returncode
    finally:
        for process,_ in loads:
            if process.poll() is None:
                process.terminate()
                try:process.communicate(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.communicate()


def worker_summary(events):
    process=next(e for e in events if e['event']=='process')
    if not process['rusage_v6']:raise RuntimeError('Process scheduler counters unavailable')
    scale=process['mach_numer']/process['mach_denom']
    cpu=(process['user_mach']+process['system_mach'])*scale/1e9
    runnable=process['runnable_raw']*scale/1e9
    groups={}
    for row in events:
        if row['event']!='worker':continue
        library=Path(row['library']).name
        key=library+'/'+str(row['offset'])
        group=groups.setdefault(key,{'library':library,'offset':row['offset'],'names':[],'workers':0,
                                     'cpu_seconds':0,'condition_seconds':0,'mutex_seconds':0,'wall_seconds':0})
        group['workers']+=1
        if row['name'] not in group['names']:group['names'].append(row['name'])
        for source,target in (('cpu_ns','cpu_seconds'),('condition_ns','condition_seconds'),('mutex_ns','mutex_seconds'),('wall_ns','wall_seconds')):
            group[target]+=row[source]/1e9
    lifetime=next(e for e in events if e['event']=='process_lifetime')
    lifetime_cpu=(lifetime['user_mach']+lifetime['system_mach'])*scale/1e9
    return {'process_cpu_seconds':cpu,'process_runnable_seconds':runnable,'runqueue_wait_seconds':runnable-cpu,
            'p_core_cpu_fraction':(process['p_user_mach']+process['p_system_mach'])/(process['user_mach']+process['system_mach']),
            'instructions':process['instructions'],'cycles':process['cycles'],
            'p_instructions_fraction':process['p_instructions']/process['instructions'],
            'page_wait_seconds':process['page_wait_mach']*scale/1e9,'pageins':process['pageins'],
            'disk_read_bytes':process['disk_read_bytes'],'input_frames':process['input_frames'],'groups':groups,
            'lifetime_wall_seconds':lifetime['wall_mach']*scale/1e9,'lifetime_cpu_seconds':lifetime_cpu,
            'lifetime_runqueue_wait_seconds':lifetime['runnable_mach']*scale/1e9-lifetime_cpu,
            'lifetime_page_wait_seconds':lifetime['page_wait_mach']*scale/1e9,
            'startup_cpu_seconds':lifetime['startup_cpu_mach']*scale/1e9,
            'startup_page_wait_seconds':lifetime['startup_page_wait_mach']*scale/1e9,
            'startup_pageins':lifetime['startup_pageins'],
            'warning':'Worker wait wall includes mutex reacquisition and wake scheduling; it overlaps worker CPU. Residual wall is not a direct runnable-wait measurement.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--child',type=Path)
    parser.add_argument('--mode',choices=('profile','replay'),default='profile')
    parser.add_argument('--blocks',type=int,choices=(1,2,3,4,6),default=1)
    parser.add_argument('--profile',choices=('hd60','raw30'))
    parser.add_argument('--load',type=int,choices=(0,2),action='append')
    args=parser.parse_args()
    if args.child:return child(args.child)
    from ffv2.config import check_mounts
    from ffv2.engine import selection,library_closure
    from ffv2.resources import Policy,snapshot
    from verify_phase2 import Verification
    from profile_phase9 import counters
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    retained=read(Path(str(lab_path('ffmpeg-v2-phase9/reproduce-20261104T031956-d74be804/report.json'))))
    for path,checksum in retained['sources'].items():
        if sha256_file(Path(path))!=checksum:raise RuntimeError('Retained source changed')
    specifications=retained['specifications']
    if args.profile:specifications={args.profile:specifications[args.profile]}
    loads=args.load or [0,2]
    selected=selection(verify_hashes=True)
    binaries={'native':selected['binaries']['ffmpeg'],'stock':'/opt/homebrew/bin/ffmpeg'}
    tools={'observer':WORK/'tools-v4/worker_probe.dylib','load':WORK/'tools-v2/cpu_load'}
    tool_hashes={k:sha256_file(v) for k,v in tools.items()}
    closures={label:library_closure([Path(binary)]) for label,binary in binaries.items()}
    directory=WORK/(args.mode+'-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory);directory.mkdir(mode=0o700)
    reasons=Policy().admission(snapshot(directory),2*1024**3,4*1024**3)
    if reasons:raise RuntimeError(str(reasons))
    verify=Verification(Path(selected['install_prefix']),directory/'guarded')
    report={'status':'running','mode':args.mode,'directory':str(directory),'specifications':specifications,
            'load_levels':loads,'blocks':args.blocks,'rows':[],'engine_files':closures,'tool_sha256':tool_hashes,
            'runner_sha256':sha256_file(Path(__file__)),'initial_resources':snapshot(directory).json(),
            'scope':'No-added-load is not an idle host. Own two 50% wall-duty workers are measured. Instrumented profiling is excluded from speed promotion. All slow measured runs retained.'}
    target=directory/'report.json'
    def save():write_json(target,report)
    def run(profile,load,label,block,slot,warmup):
        identity=f'{profile}-load{load}-{label}-{block}-{slot}'
        output=directory/(identity+'.mp4');trace=directory/(identity+'.workers.jsonl')
        request={'binary':binaries[label],'argv':specifications[profile]['argv'],'output':str(output),
                 'load_workers':load,'load_binary':str(tools['load']),'load_prefix':str(directory/(identity+'.load')),
                 'observer':str(tools['observer']),'trace':str(trace),'profiled':args.mode=='profile',
                 'child_report':str(directory/(identity+'.child.json'))}
        request_path=directory/(identity+'.request.json');write_json(request_path,request)
        receipt=verify.aux(identity,[sys.executable,'-B',str(Path(__file__)), '--child',str(request_path)],output,timeout=1200,budget=256*1024**2)
        if int(receipt['last_progress']['frame'])!=specifications[profile]['frames']:raise RuntimeError('Frame coverage failed')
        if sha256_file(output)!=specifications[profile]['reference_sha256']:raise RuntimeError('Baseline bit identity changed')
        child_report=read(request['child_report']);counts=counters(receipt['stderr_tail'])
        row={'profile':profile,'load':load,'label':label,'block':block,'slot':slot,'warmup':warmup,
             'seconds':child_report['encoding_wall_seconds'],'counters':counts,'output':str(output),'sha256':sha256_file(output),
             'child_report':request['child_report'],'child_sha256':sha256_file(Path(request['child_report'])),
             'receipt':str(next((directory/'guarded').glob(identity+'-*.diagnostic.json'))),
             'host_load_average':os.getloadavg(),'peak_job_memory_bytes':receipt['peak_job_memory_bytes']}
        if args.mode=='profile':
            if trace.stat().st_size>2*1024**2:raise RuntimeError('Observer budget exceeded')
            events=[json.loads(line) for line in trace.read_text().splitlines()];summary=worker_summary(events)
            if summary['input_frames']!=specifications[profile]['frames']:raise RuntimeError('Observer frame coverage failed')
            row.update(worker_summary=summary,trace=str(trace),trace_sha256=sha256_file(trace))
        report['rows'].append(row);save()
        print(json.dumps({'profile':profile,'load':load,'label':label,'seconds':round(row['seconds'],3),
                          'profiled':args.mode=='profile','block':block}),flush=True)
    try:
        save()
        if args.mode=='replay':
            for profile in specifications:
                for load in loads:
                    for slot,label in enumerate(binaries):run(profile,load,label,-1,slot,True)
        rng=random.Random(2026110410)
        for block in range(args.blocks):
            groups=[(profile,load) for profile in specifications for load in loads];rng.shuffle(groups)
            for index,(profile,load) in enumerate(groups):
                order=('native','stock','stock','native') if (block+index)%2 else ('stock','native','native','stock')
                for slot,label in enumerate(order):run(profile,load,label,block,slot,args.mode=='profile')
        if sha256_file(Path(__file__))!=report['runner_sha256']:raise RuntimeError('Runner changed')
        if tool_hashes!={k:sha256_file(v) for k,v in tools.items()}:raise RuntimeError('Diagnostic tools changed')
        for label,binary in binaries.items():
            if library_closure([Path(binary)])!=closures[label]:raise RuntimeError('Engine closure changed')
        report['status']='completed';save()
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);save();raise
    print(json.dumps({'report':str(target),'cases':len(report['rows'])}))
    return 0


if __name__=='__main__':sys.exit(main())
