#!/usr/bin/python3 -B
"""Generate bounded complete quality outputs independently from timing validity."""
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

from phase11_common import ROOT,WORK,read,guarded
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',required=True,type=Path);args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    candidate=read(args.candidate)
    if candidate.get('profile_instrumented'):raise RuntimeError('Training instrumentation is not a final candidate')
    selected=selection(verify_hashes=True)
    previous=read(Path(str(lab_path('ffmpeg-v2-phase10/confirm-candidate-20261104T065052-21da9545/report.json'))))
    specifications=previous['specifications']
    retained=read(Path(str(lab_path('ffmpeg-v2-phase9/reproduce-20261104T031956-d74be804/report.json'))))
    for path,checksum in retained['sources'].items():
        if sha256_file(Path(path))!=checksum:raise RuntimeError('Quality input changed')
    binaries={'original':selected['binaries']['ffmpeg'],'candidate':candidate['binaries']['ffmpeg'],'stock':'/opt/homebrew/bin/ffmpeg'}
    closures={label:library_closure([Path(binary)]) for label,binary in binaries.items()}
    directory=WORK/('quality-candidate-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8]);directory.mkdir(mode=0o700)
    report={'status':'running','phase':11,'mode':'quality','specifications':specifications,'configurations':binaries,'engine_files':closures,
            'candidate_manifest':str(args.candidate),'candidate_manifest_sha256':sha256_file(args.candidate),'rows':[],
            'scope':'Complete target outputs for quality only; CPU/load/cache timings are not promotion evidence.'}
    target=directory/'report.json';write_json(target,report);verify=Verification(Path(selected['install_prefix']),directory/'guarded')
    try:
        for profile,spec in specifications.items():
            for label,binary in binaries.items():
                output=directory/(profile+'-'+label+'.mp4')
                receipt,path=guarded(verify,profile+'-'+label,[binary,*spec['argv'],str(output)],output)
                if int(receipt['last_progress']['frame'])!=spec['frames']:raise RuntimeError('Complete quality frame coverage failed')
                checksum=sha256_file(output)
                if label in ('original','stock') and checksum!=spec['reference_sha256']:raise RuntimeError('Frozen baseline output changed')
                report['rows'].append({'profile':profile,'label':label,'warmup':True,'output':str(output),'sha256':checksum,
                    'bytes':output.stat().st_size,'receipt':str(path)})
                write_json(target,report);print(json.dumps({'profile':profile,'label':label,'sha256':checksum}),flush=True)
        for label,binary in binaries.items():
            if library_closure([Path(binary)])!=closures[label]:raise RuntimeError('Encoder closure changed')
        report['status']='completed';write_json(target,report)
        subprocess.run([sys.executable,'-B',str(ROOT/'scripts/quality_phase10.py'),str(target),'--reuse-quality',
            str(lab_path('ffmpeg-v2-phase10/smoke-candidate-20261104T055600-531ef102/quality.json'))],check=True)
    except BaseException as error:
        if report['status']!='completed':
            report.update(status='failed',error=str(error)[:4000]);write_json(target,report)
        write_json(directory/'quality-driver-failure.json',{'status':'failed','error':str(error)[:4000]});raise
    quality=read(directory/'quality.json')
    if not all(v['quality_accepted'] for v in quality['comparisons'].values()):raise RuntimeError('Quality gate rejected candidate')
    print(json.dumps({'report':str(target),'quality':str(directory/'quality.json')}))


if __name__=='__main__':main()
