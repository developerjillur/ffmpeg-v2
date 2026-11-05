#!/usr/bin/python3 -B
"""Hot-file, matched-background replay with kernel exit clocks and no injected code."""
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

from phase11_common import ROOT,WORK,read,guarded,freeze_sources
from conditions_phase11 import DEFAULT_POLICY,validate_case,validate_block
from admission_phase11 import wait_window
from cache_phase11 import ComparisonCaches
from ffv2.config import check_mounts
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from ffv2.resources import Policy,snapshot
from verify_phase2 import Verification


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('calibrate','confirm'),default='calibrate')
    parser.add_argument('--candidate',type=Path);parser.add_argument('--profile',choices=('hd60','raw30'),action='append')
    parser.add_argument('--quality',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,default=WORK/'initial.json')
    parser.add_argument('--load',type=int,choices=(0,2),action='append');parser.add_argument('--blocks',type=int,choices=(3,9),default=9)
    parser.add_argument('--max-attempts',type=int,default=27);args=parser.parse_args()
    if not args.blocks<=args.max_attempts<=45:raise ValueError('Bounded attempts required')
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    initial=read(args.baseline);selected=selection(verify_hashes=True)
    if selected['selection_id']!=initial['selection']['selection_id']:raise RuntimeError('Active baseline changed')
    candidate=read(args.candidate) if args.candidate else read(Path(str(lab_path('ffmpeg-v2-phase10/staged-engines.json'))))['rowvec']
    if candidate.get('profile_instrumented'):raise RuntimeError('Training instrumentation cannot be timed as a final candidate')
    original=read(Path(str(lab_path('ffmpeg-v2-phase10/confirm-candidate-20261104T065052-21da9545/report.json'))))
    specifications={p:original['specifications'][p] for p in args.profile or ('hd60','raw30')}
    sources={p:spec['argv'][spec['argv'].index('-i')+1] for p,spec in specifications.items()}
    retained=read(Path(str(lab_path('ffmpeg-v2-phase9/reproduce-20261104T031956-d74be804/report.json'))))
    for name,checksum in retained['sources'].items():
        if sha256_file(Path(name))!=checksum:raise RuntimeError('Retained input changed')
    tools=read(WORK/'tools-v6/report.json')
    if tools['status']!='completed':raise RuntimeError('Calibrated control program required')
    if sha256_file(Path(tools['binary']))!=tools['binary_sha256'] or sha256_file(Path(tools['load_program']))!=tools['load_sha256']:
        raise RuntimeError('Control tools changed')
    binaries={'original':selected['binaries']['ffmpeg'],'candidate':candidate['binaries']['ffmpeg'],'stock':'/opt/homebrew/bin/ffmpeg'}
    closures={key:library_closure([Path(value)]) for key,value in binaries.items()}
    quality=read(args.quality);quality_report=read(Path(quality['source_report']))
    if quality['status']!='completed' or sha256_file(Path(quality['source_report']))!=quality['source_sha256']:
        raise RuntimeError('Immutable completed quality evidence required')
    if quality_report['engine_files']!=closures or quality_report['configurations']!=binaries:
        raise RuntimeError('Quality tested a different runtime closure')
    if any(not value['quality_accepted'] for value in quality['comparisons'].values()):raise RuntimeError('Quality gate failed')
    identity=read(args.quality.with_name('decoded-identity.json'))
    if identity['status']!='completed' or identity['source_sha256']!=quality['source_sha256']:
        raise RuntimeError('Full decoded identity required')
    expected={profile:{label:next(r['sha256'] for r in quality_report['rows'] if r['profile']==profile and r['label']==label)
                      for label in binaries} for profile in specifications}
    if any(specifications[p]!=quality_report['specifications'][p] for p in specifications):raise RuntimeError('Quality workload mismatch')
    directory=WORK/(args.mode+'-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8]);check_mounts(directory);directory.mkdir(mode=0o700)
    reasons=Policy().admission(snapshot(directory),4*1024**3,8*1024**3)
    if reasons:raise RuntimeError(str(reasons))
    verify=Verification(Path(selected['install_prefix']),directory/'guarded');loads=args.load or [0,2]
    image_lists={}
    for label,closure in closures.items():
        if any('\n' in name for name in closure):raise RuntimeError('Plain image paths required')
        image_lists[label]=directory/('images-'+label+'.txt');image_lists[label].write_text('\n'.join(closure)+'\n')
    report={'status':'running','phase':11,'mode':args.mode,'directory':str(directory),'specifications':specifications,
        'baseline':{'path':str(args.baseline),'sha256':sha256_file(args.baseline)},
        'sources':{p:{'path':path,'sha256':retained['sources'][path]} for p,path in sources.items()},'configurations':binaries,
        'engine_files':closures,'load_levels':loads,'required_valid_blocks':args.blocks,'maximum_attempts_per_group':args.max_attempts,
        'environment_policy':DEFAULT_POLICY,'rows':[],'blocks':[],'tools':tools,'admissions':[],
        'automatic_admission':{'preferred_one_second_samples':8,'preferred_background_span_max':.75,'background_max':14.5,
            'preflight_global_busy_max':6.0,
            'exploratory_block_after_seconds':15,'total_wait_budget_seconds':3600,
            'scope':'Readiness scheduling only. All observed per-case and complete-block validity rules remain mandatory.'},
        'readiness_revision_records':[{'path':str(p),'sha256':sha256_file(p)} for p in sorted(WORK.glob('readiness-revision-*.json'))],
        'cache_revision_records':[{'path':str(p),'sha256':sha256_file(p)} for p in sorted(WORK.glob('cache-hold-revision-*.json'))],
        'quality':{'path':str(args.quality),'sha256':sha256_file(args.quality),'decoded_identity':str(args.quality.with_name('decoded-identity.json')),
                   'decoded_identity_sha256':sha256_file(args.quality.with_name('decoded-identity.json')),'expected_output_sha256':expected},
        'runner_sha256':sha256_file(Path(__file__)),'conditions_sha256':sha256_file(ROOT/'scripts/conditions_phase11.py'),
        'admission_sha256':sha256_file(ROOT/'scripts/admission_phase11.py'),
        'cache_helper_sha256':sha256_file(ROOT/'scripts/cache_phase11.py'),
        'scope':'Unmodified FFmpeg processes. Shared input mapping preheated outside the timed child lifetime. Entire unstable blocks retained and excluded by environment rules only; no timing-based exclusion.'}
    target=directory/'report.json'
    report['frozen_sources']=freeze_sources(directory,('benchmark_phase11.py','conditions_phase11.py','admission_phase11.py','cache_phase11.py','phase11_common.py','analyze_phase11.py'))
    def save():write_json(target,report)
    caches=ComparisonCaches(sources,set().union(*(set(c) for c in closures.values())),directory,report,save)
    def run(profile,load,label,block,attempt,slot,warmup):
        identity=f'{profile}-l{load}-{label}-b{block}-a{attempt}-s{slot}'
        output=directory/(identity+'.mp4');counter=directory/(identity+'.counter.json')
        argv=['/usr/bin/env','FFV2_BENCH_IMAGES='+str(image_lists[label]),tools['binary'],str(counter),sources[profile],str(load),tools['load_program'],'0',str(DEFAULT_POLICY['background_admission_max']),
              '--',binaries[label],*specifications[profile]['argv'],str(output)]
        receipt,path=guarded(verify,identity,argv,output,memory=8*1024**3)
        caches.current.check()
        data=read(counter);environment=validate_case(data,load)
        if data['status']=='completed' and (data['input_bytes']!=Path(sources[profile]).stat().st_size or data['image_count']!=len(closures[label])):
            raise RuntimeError('Cache conditioning covered different inputs/images')
        row={'profile':profile,'load':load,'label':label,'block':block,'attempt':attempt,'slot':slot,'warmup':warmup,
            'environment':environment,'counter':str(counter),'counter_sha256':sha256_file(counter),'receipt':str(path),
            'cache_hold_id':caches.current.record['lease_id']}
        if data['status']=='completed':
            if int((receipt.get('last_progress') or {}).get('frame',0))!=specifications[profile]['frames']:raise RuntimeError('Frame count failed')
            row.update(seconds=data['process']['wall_seconds'],output=str(output),sha256=sha256_file(output),bytes=output.stat().st_size,
                instructions=data['process']['instructions'],peak_job_memory_bytes=receipt['peak_job_memory_bytes'])
            if row['sha256']!=expected[profile][label]:raise RuntimeError('Frozen quality output changed')
        elif data['status']!='environment_rejected':raise RuntimeError('Measurement failed')
        report['rows'].append(row);save()
        print(json.dumps({'profile':profile,'load':load,'label':label,'block':block,'seconds':round(row.get('seconds',0),4),
            'valid_environment':environment['valid'],'background':round(environment.get('background_cores',-1),3),
            'disk_bytes':environment.get('disk_read_bytes'),'reasons':environment['reasons']}),flush=True)
        return row
    try:
        save()
        for profile in specifications:
            for load in loads:
                with caches.hold(profile,load,-1,-1,warmup=True):
                    for slot,label in enumerate(binaries):run(profile,load,label,-1,-1,slot,True)
        if args.mode=='confirm':
            rng=random.Random(2026110411)
            for block in range(args.blocks):
                groups=[(p,l) for p in specifications for l in loads];rng.shuffle(groups)
                for profile,load in groups:
                    completed=False
                    for attempt in range(args.max_attempts):
                        previous=sum(b['profile']==profile and b['load']==load for b in report['blocks'])
                        if previous>=args.max_attempts:break
                        labels=list(binaries);offset=(previous+block)%len(labels);labels=labels[offset:]+labels[:offset]
                        rows=[]
                        with caches.hold(profile,load,block,previous,warmup=False):
                            for slot,label in enumerate(labels+list(reversed(labels))):
                                row=run(profile,load,label,block,previous,slot,False);rows.append(row)
                                if not row['environment']['valid']:break
                        validation=validate_block(rows,list(binaries),load)
                        report['blocks'].append({'profile':profile,'load':load,'block':block,'attempt':previous,
                            'validation':validation,'rows':[r['counter'] for r in rows]});save()
                        print(json.dumps({'block':block,'profile':profile,'load':load,'attempt':previous,'validation':validation}),flush=True)
                        if validation['valid']:completed=True;break
                    if not completed:
                        report.setdefault('exhausted_groups',[])
                        key=profile+'/load'+str(load)
                        if key not in report['exhausted_groups']:report['exhausted_groups'].append(key)
                        save()
        for label,binary in binaries.items():
            if library_closure([Path(binary)])!=closures[label]:raise RuntimeError('Engine changed')
        if sha256_file(args.baseline)!=report['baseline']['sha256']:raise RuntimeError('Baseline snapshot changed')
        if sha256_file(Path(__file__))!=report['runner_sha256'] or sha256_file(ROOT/'scripts/conditions_phase11.py')!=report['conditions_sha256']:
            raise RuntimeError('Frozen measurement code changed')
        if sha256_file(ROOT/'scripts/admission_phase11.py')!=report['admission_sha256']:raise RuntimeError('Admission rules changed')
        if sha256_file(ROOT/'scripts/cache_phase11.py')!=report['cache_helper_sha256']:raise RuntimeError('Cache conditioning changed')
        if any(sha256_file(ROOT/'scripts'/name)!=record['sha256'] for name,record in report['frozen_sources'].items()):raise RuntimeError('Frozen measurement source changed')
        if (directory/'admission.jsonl').exists():report['admission_log_sha256']=sha256_file(directory/'admission.jsonl')
        report['status']='completed';save()
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);save();raise
    finally:save()
    if report['status']!='completed':raise RuntimeError(report.get('error','Incomplete comparison'))
    print(json.dumps({'report':str(target),'cases':len(report['rows'])}))


if __name__=='__main__':main()
