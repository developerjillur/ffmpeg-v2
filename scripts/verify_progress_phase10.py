#!/usr/bin/python3 -B
"""ThreadSanitizer coverage of the actual patched 8/10-bit progress functions."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import argparse
import os
from pathlib import Path
import shlex
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=('opt','row','rowvec'),default='rowvec');args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    work=Path(str(lab_path('ffmpeg-v2-phase10')))
    source=work/('x264-opt-source' if args.variant=='opt' else 'x264-row-source');build=work/('x264-build-'+args.variant)
    staged=json.loads((work/'staged-engines.json').read_text())[args.variant]
    directory=work/('progress-tsan-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700);verify=Verification(Path(staged['prefix']),directory/'guarded')
    cflags=next(line.split('=',1)[1] for line in (build/'config.mak').read_text().splitlines() if line.startswith('CFLAGS='))
    cflags=cflags.replace('$(SRCPATH)',str(source)).replace('-I.','-I'+str(build)).replace('-std=gnu99','-std=gnu11')
    flags=[*shlex.split(cflags),'-g','-O1','-fno-omit-frame-pointer','-fsanitize=thread']
    report={'status':'running','source_commit':staged['source_commit'],'directory':str(directory),'cases':[],
            'test_source_sha256':sha256_file(ROOT/'tests/native/x264_progress.c'),
            'scope':'Actual frame.c compiled with ThreadSanitizer; the rest of the unchanged codec archive is linked for dependencies. Tests cover row publication, positive blocking, negative queries and reuse, not every encoder race.'}
    target=directory/'report.json';write_json(target,report)
    try:
        for depth in (8,10):
            frame=directory/('frame-'+str(depth)+'.o');binary=directory/('progress-'+str(depth))
            bitflags=['-DBIT_DEPTH='+str(depth),'-DHIGH_BIT_DEPTH='+str(int(depth>8))]
            compile_frame=verify.aux('frame-'+str(depth),['/usr/bin/clang',*flags,*bitflags,'-c',str(source/'common/frame.c'),'-o',str(frame)],frame,timeout=180,budget=16*1024**2)
            linked=verify.aux('link-'+str(depth),['/usr/bin/clang',*flags,*bitflags,str(ROOT/'tests/native/x264_progress.c'),str(frame),str(build/'libx264.a'),'-lm','-lpthread','-o',str(binary)],binary,timeout=180,budget=64*1024**2)
            result=verify.aux('stress-'+str(depth),['/usr/bin/env','TSAN_OPTIONS=halt_on_error=1',str(binary)],binary,timeout=120,budget=64*1024**2)
            stats=json.loads(result['stderr_tail'])
            if stats['errors'] or stats['checks']!=524288 or 'WARNING: ThreadSanitizer' in result['stderr_tail']:
                raise RuntimeError('Publication stress failed')
            report['cases'].append({'depth':depth,'stats':stats,'compile':compile_frame,'link':linked,'run':result})
            write_json(target,report);print(json.dumps({'depth':depth,'stats':stats,'seconds':result['wall_seconds']}),flush=True)
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:write_json(target,report)
    print(json.dumps({'report':str(target)}))


if __name__=='__main__':main()
