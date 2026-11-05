#!/usr/bin/python3 -B
"""Guarded codec regression and live cached-progress assertions beyond HD target."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase10')))
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path);parser.add_argument('--work-root',type=Path)
    args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    stages=json.loads((WORK/'staged-engines.json').read_text());selected=selection(verify_hashes=True)
    if args.candidate:
        stages['rowvec']=json.loads(args.candidate.read_text())
        if stages['rowvec'].get('profile_instrumented'):raise RuntimeError('Final codec candidate required')
        if library_closure([Path(v) for v in stages['rowvec']['binaries'].values()])!=stages['rowvec']['files']:
            raise RuntimeError('Staged candidate changed')
    directory=(args.work_root or WORK)/('codec-regression-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700);verify=Verification(Path(stages['rowvec']['prefix']),directory/'guarded')
    engines={'original':selected['binaries']['ffmpeg'],'candidate':stages['rowvec']['binaries']['ffmpeg'],'assertions':stages['check']['binaries']['ffmpeg']}
    closures={k:library_closure([Path(v)]) for k,v in engines.items()}
    report={'status':'running','phase':11 if args.candidate else 10,'install_prefix':stages['rowvec']['prefix'],'engine_files':closures,
            'candidate_manifest':str(args.candidate) if args.candidate else None,
            'candidate_manifest_sha256':sha256_file(args.candidate) if args.candidate else None,
            'runner_sha256':sha256_file(Path(__file__)),
            'tests':{},'cases':[],'scope':'Deterministic 8/10-bit, multiple references/B-frames, slices, single-thread and interlaced regression. Assertion build must agree with production candidate and original decoded frames.'}
    target=directory/'report.json';write_json(target,report)
    try:
        sources={}
        for depth in (8,10):
            source=directory/('reference-'+str(depth)+'.mkv')
            pix='yuv420p' if depth==8 else 'yuv420p10le'
            verify.aux('fixture-'+str(depth),[engines['original'],'-v','error','-nostdin','-n','-xerror','-filter_threads','1',
                '-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=3','-frames:v','90',
                '-c:v','ffv1','-threads','1','-pix_fmt',pix,str(source)],source)
            sources[depth]=source
        modes=[('refs8',8,8,'ref=6:bframes=8'),('refs10',10,8,'ref=6:bframes=8'),
               ('sliced8',8,4,'ref=4:bframes=3:sliced-threads=1'),('single8',8,1,'ref=4:bframes=3'),
               ('interlaced8',8,4,'ref=4:bframes=3:interlaced=1:tff=1'),
               ('nondeterministic8',8,8,'ref=4:bframes=3:non-deterministic=1')]
        for name,depth,threads,params in modes:
            hashes={}
            for label,binary in engines.items():
                identity=name+'-'+label;output=directory/(identity+'.mp4');decoded=directory/(identity+'.framemd5')
                pix='yuv420p' if depth==8 else 'yuv420p10le'
                encoded=verify.aux(identity,[binary,'-v','warning','-nostdin','-n','-xerror','-filter_threads','1','-threads','2',
                    '-i',str(sources[depth]),'-an','-c:v','libx264','-preset','medium','-crf','20','-threads:v',str(threads),
                    '-pix_fmt',pix,'-x264-params',params,'-frames:v','90',str(output)],output)
                if any(message in encoded['stderr_tail'] for message in ('internal error','cached progress','Error parsing option')):
                    raise RuntimeError('Motion-vector/progress safety check fired')
                verify.aux(identity+'-decode',[engines['original'],'-v','error','-nostdin','-n','-xerror','-err_detect','explode',
                    '-threads','2','-i',str(output),'-map','0:v:0','-an','-c:v','rawvideo','-threads','1','-f','framemd5',str(decoded)],decoded)
                lines=[line for line in decoded.read_text().splitlines() if line and not line.startswith('#')]
                if len(lines)!=90:raise RuntimeError('Strict decode coverage failed')
                hashes[label]=lines
                report['cases'].append({'mode':name,'label':label,'depth':depth,'frames':90,'output':str(output),
                    'sha256':sha256_file(output),'framemd5':str(decoded),'framemd5_sha256':sha256_file(decoded),'encode_receipt':encoded})
                write_json(target,report)
            identical=hashes['candidate']==hashes['original'] and hashes['assertions']==hashes['original']
            if name!='nondeterministic8' and not identical:
                raise RuntimeError('Decoded pixels changed in '+name)
            report['tests'][name]={'status':'pass','frames_per_engine':90,'engines':3,'decoded_frames_identical':identical,
                'scope':'Full exact decoded-frame comparison' if name!='nondeterministic8' else 'Scheduling-dependent mode: strict decode and live bound assertions; no exact quality equivalence claim'}
            write_json(target,report);print(json.dumps({'mode':name,'status':'pass'}),flush=True)
        for label,binary in engines.items():
            if library_closure([Path(binary)])!=closures[label]:raise RuntimeError('Engine changed during regression')
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:write_json(target,report)
    print(json.dumps({'report':str(target),'tests':len(report['tests'])}))


if __name__=='__main__':main()
