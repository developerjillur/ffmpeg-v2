#!/usr/bin/python3 -B
"""Calibrate zombie-process counters and shared file-cache residency locally."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import argparse
import os
from pathlib import Path
import sys

from phase11_common import ROOT,WORK,read,guarded
from ffv2.engine import selection
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',choices=('v1','v2','v3','v4','v5','v6'),default='v6');args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    directory=WORK/('tools-'+args.version)
    if directory.exists():raise RuntimeError('Preserve existing tools/calibration')
    directory.mkdir(mode=0o700);selected=selection(verify_hashes=True)
    verify=Verification(Path(selected['install_prefix']),directory/'guarded')
    source=ROOT/'scripts/measure_phase11.c';binary=directory/'measure'
    load=Path(str(lab_path('ffmpeg-v2-phase10/tools-v2/cpu_load')))
    old=read(Path(str(lab_path('ffmpeg-v2-phase10/profile-20261104T054147-4f629002/report.json'))))
    if sha256_file(load)!=old['tool_sha256']['load']:raise RuntimeError('Owned load program changed')
    report={'status':'running','source_sha256':sha256_file(source),'load_program':str(load),
            'load_sha256':sha256_file(load),'calibration':[],'scope':'No FFmpeg interposition; parent reads final rusage before reaping its child. Hot-file mappings are shared and capped at 3 GiB.'}
    target=directory/'report.json';write_json(target,report)
    try:
        receipt,path=guarded(verify,'compile-control',['/usr/bin/clang','-O2','-std=gnu11','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],binary,memory=512*1024**2,budget=16*1024**2,timeout=120)
        report['compile']={'path':str(path),'sha256':sha256_file(path)};report['binary']=str(binary);report['binary_sha256']=sha256_file(binary)
        burn='import time\ne=time.process_time()+.25\nwhile time.process_time()<e: pass'
        cases=[('direct',[sys.executable,'-B','-c',burn]),
               ('descendant',[sys.executable,'-B','-c','import subprocess,sys;subprocess.run([sys.executable,"-B","-c",'+repr(burn)+'],check=True)']),
               ('short',['/usr/bin/true']),('host-cpu',[sys.executable,'-B','-c','import time;time.sleep(2)'])]
        for label,argv in cases:
            counters=directory/(label+'.json')
            result,path=guarded(verify,'calibrate-'+label,[str(binary),str(counters),str(source),'0',str(load),'0','-1','--',*argv],counters,memory=512*1024**2,budget=16*1024**2,timeout=120)
            data=read(counters)
            if data['status']!='completed' or not data['source_unchanged'] or data['resident_before']!=data['pages'] or data['resident_after']!=data['pages']:
                raise RuntimeError('Clock/cache calibration failed')
            process=data['process'];scale=data['mach_numer']/data['mach_denom']/1e9
            direct=(process['user_mach']+process['system_mach'])*scale
            child=process['child_user_raw']+process['child_system_raw']
            candidates={'mach':direct+child*scale,'nanoseconds':direct+child/1e9}
            unit=min(candidates,key=lambda k:abs(candidates[k]-process['wait4_cpu_seconds'])) if child else 'not_applicable'
            calculated=candidates[unit] if child else direct
            if abs(calculated-process['wait4_cpu_seconds'])>.003:raise RuntimeError('CPU counter units do not match wait4')
            if label=='host-cpu':
                capacities=[]
                for before,after in zip(data['samples'],data['samples'][1:]):
                    elapsed=after['seconds']-before['seconds']
                    if elapsed<.20:continue
                    ticks=sum((b-a)&0xffffffff for a,b in zip(before['ticks'],after['ticks']))
                    capacities.append(ticks/data['clock_ticks']/elapsed)
                if len(capacities)<6 or any(not data['logical_cpus']-1.2<=v<=data['logical_cpus']+1.2 for v in capacities):
                    raise RuntimeError('CPU counter cadence is stale or inconsistent')
                report['host_cpu_capacity_samples']=capacities
            report['calibration'].append({'label':label,'counter':str(counters),'sha256':sha256_file(counters),
                'wall_seconds':process['wall_seconds'],'wait4_cpu_seconds':process['wait4_cpu_seconds'],'calculated_cpu_seconds':calculated,
                'child_time_unit':unit,'receipt':str(path)})
            write_json(target,report);print(json.dumps({'calibration':label,'wall_seconds':process['wall_seconds'],'child_unit':unit}),flush=True)
        report['child_time_unit']=next(r['child_time_unit'] for r in report['calibration'] if r['label']=='descendant')
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:write_json(target,report)
    print(json.dumps({'tools':str(target),'status':report['status']}))


if __name__=='__main__':main()
