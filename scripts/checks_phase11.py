#!/usr/bin/python3 -B
"""Run sequential quality controls while an owned, idle admission monitor waits."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from phase11_common import ROOT,WORK,read
from ffv2.config import Settings
from ffv2.darwin import process_info
from ffv2.io import sha256_file,write_json
from ffv2.worker import host_lock


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--monitor-pid',required=True,type=int)
    parser.add_argument('--monitor-birth',required=True,type=int);parser.add_argument('--candidate',required=True,type=Path)
    parser.add_argument('--workflow-smoke',action='store_true');parser.add_argument('--quality',type=Path)
    args=parser.parse_args();os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    directory=WORK/('checks-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8]);directory.mkdir(mode=0o700)
    report={'status':'running','monitor_pid':args.monitor_pid,'monitor_birth':args.monitor_birth,'steps':[]}
    target=directory/'report.json';paused=False;started=time.monotonic()
    def same():
        value=process_info(args.monitor_pid)
        return value and value['start_abstime']==args.monitor_birth and not value['exit_abstime']
    try:
        if not same():raise RuntimeError('Owned monitor identity changed')
        command=subprocess.check_output(['/bin/ps','-p',str(args.monitor_pid),'-o','command='],text=True).strip()
        if ' -B FFmpeg-v2/scripts/benchmark_phase11.py --mode confirm ' not in command:raise RuntimeError('Unexpected monitor command')
        os.kill(args.monitor_pid,signal.SIGSTOP);paused=True
        pairs=[tuple(map(int,line.split())) for line in subprocess.check_output(['/bin/ps','-axo','pid=,ppid='],text=True).splitlines()]
        if any(parent==args.monitor_pid for pid,parent in pairs):raise RuntimeError('Monitor was not idle; resume without overlapping work')
        with host_lock(Settings.load()):pass
        report['pause_started_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());write_json(target,report)
        candidate=read(args.candidate)
        commands=[('codec',[sys.executable,'-B',str(ROOT/'scripts/verify_x264_phase10.py'),'--candidate',str(args.candidate),'--work-root',str(WORK)]),
            ('native',[sys.executable,'-B',str(ROOT/'scripts/verify_native_media.py'),'--prefix',candidate['prefix']])]
        if args.workflow_smoke:
            if not args.quality:raise ValueError('Quality evidence required for workflow smoke')
            commands=[('workflow-calibration',[sys.executable,'-B',str(ROOT/'scripts/workflow_phase11.py'),'--mode','calibrate','--candidate',str(args.candidate),'--quality',str(args.quality)])]
        for name,argv in commands:
            log=directory/(name+'.log');environment=os.environ.copy();environment['FFV2_STATE_DIR']=str(WORK/'native-state')
            with log.open('xb') as stream:done=subprocess.run(argv,env=environment,stdout=stream,stderr=stream,timeout=900)
            step={'name':name,'exit_code':done.returncode,'log':str(log),'sha256':sha256_file(log)}
            if done.returncode:
                report['steps'].append(step);raise RuntimeError(name+' control failed: '+log.read_text()[-2000:])
            content=log.read_text()
            value=json.loads(content) if name=='native' else json.loads(content.splitlines()[-1])
            step['report']=str(Path(value['directory'])/'report.json') if name=='native' else value['report']
            step['report_sha256']=sha256_file(Path(step['report']));report['steps'].append(step);write_json(target,report)
            print(json.dumps(step),flush=True)
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:
        if paused and same():os.kill(args.monitor_pid,signal.SIGCONT);report['monitor_resumed']=True
        report['pause_elapsed_seconds']=time.monotonic()-started;write_json(target,report)
    print(json.dumps({'report':str(target),'monitor_resumed':report.get('monitor_resumed',False)}))


if __name__=='__main__':main()
