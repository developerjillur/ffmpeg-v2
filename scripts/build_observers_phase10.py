#!/usr/bin/python3 -B
"""Bind each observer to exactly the profiled encoder's private dependency."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase10')))
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def main():
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    selected=selection(verify_hashes=True);stages=json.loads((WORK/'staged-engines.json').read_text())
    directory=WORK/'tools-v5'
    if directory.exists():raise RuntimeError('Preserve existing observer build')
    directory.mkdir(mode=0o700);verify=Verification(Path(selected['install_prefix']),directory/'guarded')
    report={'status':'running','source_sha256':sha256_file(ROOT/'scripts/worker_probe_phase10.c'),'tools':{}}
    target=directory/'report.json';write_json(target,report)
    try:
        for label,prefix in (('original',Path('/opt/homebrew/opt/x264')),('base',Path(stages['base']['prefix'])),('candidate',Path(stages['rowvec']['prefix']))):
            dependency=(prefix/'lib/libx264.165.dylib').resolve(strict=True)
            for mode in ('worker','process'):
                output=directory/(mode+'-'+label+'.dylib')
                argv=['/usr/bin/clang','-O2','-Wall','-Wextra','-Wno-unused-function','-dynamiclib','-I'+str(prefix/'include')]
                if mode=='process':argv+=['-DFFV2_PROCESS_ONLY=1']
                argv += [str(ROOT/'scripts/worker_probe_phase10.c'),str(dependency),'-o',str(output)]
                receipt=verify.aux('build-'+mode+'-'+label,argv,output,timeout=120,budget=16*1024**2)
                closure=library_closure([output]);encoders=[Path(p) for p in closure if 'libx264' in Path(p).name]
                if encoders!=[dependency]:raise RuntimeError('Observer has a different encoder dependency')
                report['tools'][mode+'/'+label]={'path':str(output),'sha256':sha256_file(output),'encoder':str(dependency),'files':closure,'receipt':receipt}
                write_json(target,report)
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:write_json(target,report)
    print(json.dumps({'report':str(target),'tools':len(report['tools'])}))


if __name__=='__main__':main()
