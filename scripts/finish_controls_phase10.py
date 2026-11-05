#!/usr/bin/python3 -B
"""Sequential post-confirmation controls; no activation or installation."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase10')))
sys.path.insert(0,str(ROOT))
from ffv2.io import write_json,sha256_file


def main():
    parser=argparse.ArgumentParser();parser.add_argument('confirmation',type=Path);args=parser.parse_args()
    source=json.loads(args.confirmation.read_text())
    if source['status']!='completed' or source['mode']!='confirm':raise RuntimeError('Finished confirmation required')
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    directory=WORK/('controls-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8]);directory.mkdir(mode=0o700)
    report={'status':'running','phase':10,'confirmation':str(args.confirmation),'confirmation_sha256':sha256_file(args.confirmation),'steps':[]}
    candidate=json.loads((WORK/'staged-engines.json').read_text())['rowvec']['prefix']
    target=directory/'report.json';write_json(target,report)
    commands=[
        ('quality',[sys.executable,'-B',str(ROOT/'scripts/quality_phase10.py'),str(args.confirmation),'--reuse-quality',str(WORK/'smoke-candidate-20261104T055600-531ef102/quality.json')],1200),
        ('analysis',[sys.executable,'-B',str(ROOT/'scripts/analyze_phase10.py'),str(args.confirmation)],120),
        ('decoded-identity',[sys.executable,'-B',str(ROOT/'scripts/verify_identity_phase10.py'),str(args.confirmation)],1200),
        ('progress-negative-publication',[sys.executable,'-B',str(ROOT/'scripts/verify_progress_phase10.py'),'--variant','rowvec'],300),
        ('build-observers',[sys.executable,'-B',str(ROOT/'scripts/build_observers_phase10.py')],300),
        ('worker-profile',[sys.executable,'-B',str(ROOT/'scripts/benchmark_phase10.py'),'--mode','profile','--candidate-key','rowvec'],1200),
        ('process-profile',[sys.executable,'-B',str(ROOT/'scripts/benchmark_phase10.py'),'--mode','profile','--candidate-key','rowvec','--process-only'],1200),
        ('codec-regression',[sys.executable,'-B',str(ROOT/'scripts/verify_x264_phase10.py')],1200),
        ('full-workflow',[sys.executable,'-B',str(ROOT/'scripts/workflow_phase10.py'),'--blocks','7'],2400),
        ('native-cli-mcp',['/usr/bin/env','FFV2_STATE_DIR='+str(WORK/'native-state'),sys.executable,'-B',str(ROOT/'scripts/verify_native_media.py'),'--prefix',candidate],1200),
        ('unit-matrix',[sys.executable,'-B',str(ROOT/'scripts/verify_unit_matrix.py'),'--work-root',str(WORK)],150)]
    try:
        for name,argv,timeout in commands:
            log=directory/(name+'.log');row={'name':name,'argv':argv,'status':'running','log':str(log)}
            report['steps'].append(row);write_json(target,report)
            print(json.dumps({'step':name,'status':'running'}),flush=True)
            with log.open('xb') as stream:
                completed=subprocess.run(argv,stdout=stream,stderr=subprocess.STDOUT,cwd=ROOT,timeout=timeout)
            row.update(exit_code=completed.returncode,sha256=sha256_file(log),status='completed' if completed.returncode==0 else 'failed')
            write_json(target,report)
            if completed.returncode:raise RuntimeError(name+': '+log.read_text()[-3000:])
            print(json.dumps({'step':name,'status':'completed'}),flush=True)
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:write_json(target,report)
    print(json.dumps({'controls':str(target)}))


if __name__=='__main__':main()
