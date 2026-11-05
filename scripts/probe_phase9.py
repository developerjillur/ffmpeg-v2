#!/usr/bin/python3 -B
"""Excluded native/Stock feed probes; exact output identity guards the observer."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.config import check_mounts
from ffv2.engine import selection
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def main():
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    selected=selection(verify_hashes=True)
    source=Path(str(lab_path('ffmpeg-v2-phase9/reproduce-20261104T031956-d74be804/report.json')))
    baseline=json.loads(source.read_text())
    assert baseline['status']=='completed'
    directory=source.parent.parent/('probe-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory);directory.mkdir(mode=0o700)
    verify=Verification(Path(selected['install_prefix']),directory)
    library=directory/'feed_probe.dylib'
    compile_receipt=verify.aux('compile-probe',['/usr/bin/clang','-dynamiclib','-O2','-std=c11','-Wall','-Wextra',
        '-I/opt/homebrew/include',str(ROOT/'scripts/feed_probe.c'),'-L/opt/homebrew/lib','-lx264','-o',str(library)],library,
        timeout=120,budget=2*1024**2)
    report={'status':'running','scope':'Injected observer only; no timings promoted. CPU flags/preset/pools unmodified; output SHA must match uninstrumented baseline.',
        'source_report':str(source),'source_sha256':sha256_file(source),'observer_source_sha256':sha256_file(ROOT/'scripts/feed_probe.c'),
        'observer_library':str(library),'observer_sha256':sha256_file(library),'compile_receipt':compile_receipt,'cases':[]}
    target=directory/'probe.json';write_json(target,report)
    try:
        for profile,spec in baseline['specifications'].items():
            for label,binary in (('native',selected['binaries']['ffmpeg']),('stock','/opt/homebrew/bin/ffmpeg')):
                trace=directory/(profile+'-'+label+'.jsonl');output=directory/(profile+'-'+label+'.mp4')
                receipt=verify.aux(profile+'-'+label,['/usr/bin/env','DYLD_INSERT_LIBRARIES='+str(library),
                    'FFV2_FEED_TRACE='+str(trace),binary,*spec['argv'],str(output)],output,timeout=1200,budget=256*1024**2)
                if sha256_file(output)!=spec['reference_sha256'] or not trace.exists():
                    raise RuntimeError('Observer did not load or changed encoded output')
                events=[json.loads(x) for x in trace.read_text().splitlines()]
                if not any(x['event']=='open' for x in events) or not any(x['event']=='frame' for x in events):
                    raise RuntimeError('Encoder observer events absent')
                timing=[x for x in events if x['event']=='timing']
                if len(timing)!=1 or timing[0]['input_frames']!=spec['frames']:
                    raise RuntimeError('Observer did not cover every input frame')
                report['cases'].append({'profile':profile,'label':label,'trace':str(trace),'trace_sha256':sha256_file(trace),
                    'output':str(output),'output_sha256':sha256_file(output),'events':events})
                write_json(target,report)
                print(json.dumps({'profile':profile,'engine':label,'encoder':[x for x in events if x['event']=='open'],
                    'frames':[x for x in events if x['event']=='frame'],'timing':timing}),flush=True)
        report['status']='completed';write_json(target,report)
    except BaseException as error:
        report.update(status='failed',error=str(error)[:4000]);write_json(target,report);raise
    print(json.dumps({'report':str(target),'cases':len(report['cases'])}))


if __name__=='__main__':main()
