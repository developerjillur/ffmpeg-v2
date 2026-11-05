#!/usr/bin/python3 -B
"""Uninstrumented candidate controls and excluded attribution profiles."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import random
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase10')))
sys.path.insert(0,str(ROOT))
from ffv2.config import check_mounts
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from ffv2.resources import Policy,snapshot
from verify_phase2 import Verification
from profile_phase9 import counters
from replay_phase10 import worker_summary


def read(path):return json.loads(Path(path).read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('smoke','profile','confirm'),default='smoke')
    parser.add_argument('--blocks',type=int,choices=(1,2,3,5,7,9),default=3)
    parser.add_argument('--load',type=int,choices=(0,2),action='append')
    parser.add_argument('--profile',choices=('hd60','raw30'),action='append')
    parser.add_argument('--include-build-control',action='store_true')
    parser.add_argument('--candidate-key',choices=('opt','m4','m4safe','row','rowvec','check'),default='rowvec')
    parser.add_argument('--process-only',action='store_true')
    args=parser.parse_args();os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    if args.candidate_key=='check' and args.mode!='smoke':raise RuntimeError('Assertion build is diagnostic only')
    if args.process_only and args.mode!='profile':raise RuntimeError('Process observer is diagnostic only')
    initial=read(WORK/'initial.json');selected=selection(verify_hashes=True)
    if selected['selection_id']!=initial['selection']['selection_id']:raise RuntimeError('Frozen native selection changed')
    staged=read(WORK/'staged-engines.json')
    previous=read(Path(str(lab_path('ffmpeg-v2-phase9/reproduce-20261104T031956-d74be804/report.json'))))
    specifications={key:previous['specifications'][key] for key in args.profile or ('hd60','raw30')}
    for name,checksum in previous['sources'].items():
        if sha256_file(Path(name))!=checksum:raise RuntimeError('Retained source changed')
    binaries={'original':selected['binaries']['ffmpeg'],'base':staged['base']['binaries']['ffmpeg'],
              'candidate':staged[args.candidate_key]['binaries']['ffmpeg'],'stock':'/opt/homebrew/bin/ffmpeg'}
    if args.mode=='confirm' and not args.include_build_control:del binaries['base']
    if args.mode=='profile':binaries={k:v for k,v in binaries.items() if k in (('original','candidate','stock') if args.process_only else ('base','candidate'))}
    observer_build=read(WORK/'tools-v5/report.json') if args.mode=='profile' else None
    if observer_build and observer_build['status']!='completed':raise RuntimeError('Completed per-engine observer build required')
    closures={label:library_closure([Path(binary)]) for label,binary in binaries.items()}
    directory=WORK/(args.mode+'-candidate-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory);directory.mkdir(mode=0o700)
    reasons=Policy().admission(snapshot(directory),2*1024**3,4*1024**3)
    if reasons:raise RuntimeError(str(reasons))
    verify=Verification(Path(selected['install_prefix']),directory/'guarded')
    loads=args.load or ([0] if args.mode=='smoke' else [0,2])
    report={'status':'running','phase':10,'mode':args.mode,'directory':str(directory),'specifications':specifications,
            'load_levels':loads,'blocks':args.blocks,'candidate_key':args.candidate_key,'configurations':binaries,'engine_files':closures,'rows':[],
            'runner_sha256':sha256_file(Path(__file__)),'child_runner_sha256':sha256_file(ROOT/'scripts/replay_phase10.py'),
            'observer_mode':'process-only' if args.process_only else 'worker' if args.mode=='profile' else None,
            'observer_build_sha256':sha256_file(WORK/'tools-v5/report.json') if observer_build else None,
            'quality_status':'pending all-frame identity/metric verification; changed codec metadata alone does not waive quality gates',
            'scope':'Same encoding argv and nominal pools for all. Private base/opt use matched compiler flags. Profile/smoke excluded from acceptance. No-added-load does not imply an idle host.'}
    target=directory/'report.json'
    def save():write_json(target,report)
    def run(profile,load,label,block,slot,warmup):
        identity=f'{profile}-load{load}-{label}-{block}-{slot}'
        output=directory/(identity+'.mp4');trace=directory/(identity+'.workers.jsonl')
        observer=observer_build['tools'][('process' if args.process_only else 'worker')+'/'+('original' if label=='stock' else label)] if observer_build else None
        request={'binary':binaries[label],'argv':specifications[profile]['argv'],'output':str(output),
            'load_workers':load,'load_binary':str(WORK/'tools-v2/cpu_load'),'load_prefix':str(directory/(identity+'.load')),
            'observer':observer['path'] if observer else str(WORK/'tools-v4/worker_probe.dylib'),'trace':str(trace),'profiled':args.mode=='profile',
            'child_report':str(directory/(identity+'.child.json'))}
        path=directory/(identity+'.request.json');write_json(path,request)
        receipt=verify.aux(identity,[sys.executable,'-B',str(ROOT/'scripts/replay_phase10.py'),'--child',str(path)],output,timeout=1200,budget=256*1024**2)
        if int(receipt['last_progress']['frame'])!=specifications[profile]['frames']:raise RuntimeError('Full frame coverage failed')
        counts=counters(receipt['stderr_tail']);child=read(request['child_report'])
        row={'profile':profile,'load':load,'label':label,'block':block,'slot':slot,'warmup':warmup,
            'seconds':child['encoding_wall_seconds'],'counters':counts,'output':str(output),'sha256':sha256_file(output),
            'bytes':output.stat().st_size,'child_report':request['child_report'],
            'reference_bit_identical':sha256_file(output)==specifications[profile]['reference_sha256'],
            'receipt':str(next((directory/'guarded').glob(identity+'-*.diagnostic.json'))),'peak_job_memory_bytes':receipt['peak_job_memory_bytes']}
        if args.mode=='profile':
            events=[json.loads(line) for line in trace.read_text().splitlines()]
            expected=Path(observer['encoder']).resolve(strict=True)
            images={Path(e['path']).resolve(strict=True) for e in events if e['event']=='encoder_image'}
            actual=[e for e in events if e['event']=='encoder']
            if images!={expected} or len(actual)!=1 or Path(actual[0]['parameter_library']).resolve(strict=True)!=expected:
                raise RuntimeError('Runtime observer/encoder binding is ambiguous')
            summary=worker_summary(events)
            if summary['input_frames']!=specifications[profile]['frames'] or sha256_file(Path(observer['path']))!=observer['sha256']:
                raise RuntimeError('Observer identity/frame coverage failed')
            expected_sha=specifications[profile]['reference_sha256'] if label in ('original','stock') else next(r['sha256'] for r in read(WORK/'smoke-candidate-20261104T063905-c831595d/report.json')['rows'] if r['profile']==profile and r['label']==label)
            if row['sha256']!=expected_sha:raise RuntimeError('Profile used a different encoding implementation')
            row.update(worker_summary=summary,trace=str(trace),trace_sha256=sha256_file(trace),observer=observer['path'],observer_sha256=observer['sha256'],encoder_library=str(expected))
        report['rows'].append(row);save()
        print(json.dumps({'profile':profile,'load':load,'label':label,'block':block,'seconds':round(row['seconds'],3),
                          'instructions_billion':round(counts['instructions_retired']/1e9,3),'reference_sha_equal':row['reference_bit_identical']}),flush=True)
    try:
        save()
        for profile in specifications:
            for load in loads:
                for slot,label in enumerate(binaries):run(profile,load,label,-1,slot,True)
        if args.mode=='confirm':
            rng=random.Random(20261104101)
            for block in range(args.blocks):
                groups=[(p,l) for p in specifications for l in loads];rng.shuffle(groups)
                for profile,load in groups:
                    labels=list(binaries);offset=block%len(labels);labels=labels[offset:]+labels[:offset]
                    for slot,label in enumerate(labels+list(reversed(labels))):run(profile,load,label,block,slot,False)
        for profile in specifications:
            for label in binaries:
                hashes={r['sha256'] for r in report['rows'] if r['profile']==profile and r['label']==label}
                if len(hashes)!=1:raise RuntimeError('Non-deterministic encoded output')
        if sha256_file(Path(__file__))!=report['runner_sha256'] or sha256_file(ROOT/'scripts/replay_phase10.py')!=report['child_runner_sha256']:
            raise RuntimeError('Measurement runner changed')
        for label,binary in binaries.items():
            if library_closure([Path(binary)])!=closures[label]:raise RuntimeError('Runtime dependency set changed')
        report['status']='completed';save()
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);save();raise
    print(json.dumps({'report':str(target),'cases':len(report['rows'])}))


if __name__=='__main__':main()
