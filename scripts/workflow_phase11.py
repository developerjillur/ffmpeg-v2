#!/usr/bin/python3 -B
"""Conditioned complete HD workflow, with inclusive child CPU accounting."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from phase11_common import ROOT,WORK,read,freeze_sources
from admission_phase11 import wait_window
from cache_phase11 import ComparisonCaches
from conditions_phase11 import DEFAULT_POLICY,validate_case,validate_block
from ffv2.config import check_mounts
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from ffv2.resources import Policy,snapshot,process_memory


def watched(argv,stdout,stderr,directory):
    """Do not hold the SDK host lock while its own worker needs that lock."""
    policy=Policy();baseline=snapshot(directory)
    reasons=policy.admission(baseline,4*1024**3,512*1024**2)
    if reasons:raise RuntimeError(str(reasons))
    peak=0;started=time.monotonic();checks=0
    with stdout.open('xb') as out,stderr.open('xb') as err:
        child=subprocess.Popen(argv,stdout=out,stderr=err,start_new_session=True)
        try:
            while child.poll() is None:
                memory,method=process_memory(child.pid,additional=(os.getpid(),));peak=max(peak,memory)
                reasons=policy.running(snapshot(directory),baseline,memory)
                if method=='unavailable':reasons.append('job_memory_measurement_unavailable')
                if time.monotonic()-started>1200:reasons.append('workflow_deadline')
                checks+=1
                if reasons:raise RuntimeError(str(reasons))
                time.sleep(.25)
            if child.returncode:raise RuntimeError('Owned workflow failed: '+stderr.read_text()[-3000:])
        finally:
            if child.poll() is None:
                os.killpg(child.pid,signal.SIGTERM)
                try:child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
    return {'exit_code':child.returncode,'peak_job_memory_bytes':peak,'watchdog_checks':checks,
            'system_memory_checks_ignored':policy.ignore_system_memory,'resources_before':baseline.json(),
            'resources_after':snapshot(directory).json()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--candidate',required=True,type=Path)
    parser.add_argument('--mode',choices=('calibrate','confirm'),default='confirm')
    parser.add_argument('--quality',required=True,type=Path);parser.add_argument('--max-attempts',type=int,default=45)
    parser.add_argument('--baseline',type=Path,default=WORK/'initial.json')
    args=parser.parse_args()
    if not 9<=args.max_attempts<=45:raise ValueError('Nine to 45 bounded attempts required')
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    initial=read(args.baseline);selected=selection(verify_hashes=True);candidate=read(args.candidate)
    if selected['selection_id']!=initial['selection']['selection_id'] or candidate.get('profile_instrumented'):
        raise RuntimeError('Frozen active baseline and final candidate required')
    quality=read(args.quality);qreport=read(quality['source_report']);decoded=args.quality.with_name('decoded-identity.json')
    if quality['status']!='completed' or quality['source_sha256']!=sha256_file(Path(quality['source_report'])):
        raise RuntimeError('Immutable complete quality evidence required')
    if not all(v['quality_accepted'] for v in quality['comparisons'].values()) or read(decoded)['status']!='completed':
        raise RuntimeError('Quality/decoded identity failed')
    binaries={'original':selected['binaries'],'candidate':candidate['binaries'],
              'stock':{n:'/opt/homebrew/bin/'+n for n in ('ffmpeg','ffprobe')}}
    closures={label:library_closure([Path(value[n]) for n in ('ffmpeg','ffprobe')]) for label,value in binaries.items()}
    for label,value in binaries.items():
        if value['ffmpeg']!=qreport['configurations'][label] or library_closure([Path(value['ffmpeg'])])!=qreport['engine_files'][label]:
            raise RuntimeError('Quality tested a different encoder')
    spec=qreport['specifications']['hd60'];source=spec['argv'][spec['argv'].index('-i')+1]
    old=read(Path(str(lab_path('ffmpeg-v2-phase9/reproduce-20261104T031956-d74be804/report.json'))))
    if sha256_file(Path(source))!=old['sources'][source]:raise RuntimeError('Frozen source changed')
    expected={label:next(r['sha256'] for r in qreport['rows'] if r['profile']=='hd60' and r['label']==label) for label in binaries}
    tools=read(WORK/'tools-v6/report.json')
    if tools['status']!='completed' or tools['binary_sha256']!=sha256_file(Path(tools['binary'])) or tools['load_sha256']!=sha256_file(Path(tools['load_program'])):
        raise RuntimeError('Calibrated control tools changed')
    directory=WORK/('workflow-'+args.mode+'-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8]);check_mounts(directory);directory.mkdir(mode=0o700)
    package={p.name:sha256_file(p) for p in sorted((ROOT/'ffv2').glob('*.py'))}
    image_lists={}
    for label,closure in closures.items():
        if any('\n' in name for name in closure):raise RuntimeError('Plain image paths required')
        path=directory/('images-'+label+'.txt');path.write_text('\n'.join(closure)+'\n');image_lists[label]=path
    report={'status':'running','phase':11,'mode':args.mode,'pipeline':True,'directory':str(directory),
        'baseline':{'path':str(args.baseline),'sha256':sha256_file(args.baseline)},
        'specifications':{'hd60':spec},'sources':{'hd60':{'path':source,'sha256':old['sources'][source]}},
        'configurations':binaries,'engine_files':closures,'package':str(ROOT),'package_source_sha256':package,
        'required_valid_blocks':9,'maximum_attempts_per_group':args.max_attempts,'load_levels':[0,2],
        'environment_policy':DEFAULT_POLICY,'rows':[],'blocks':[],'admissions':[],
        'quality':{'path':str(args.quality),'sha256':sha256_file(args.quality),'decoded_identity':str(decoded),
            'decoded_identity_sha256':sha256_file(decoded),'expected_output_sha256':{'hd60':expected}},
        'tools':tools,'runner_sha256':sha256_file(Path(__file__)),
        'condition_sha256':sha256_file(ROOT/'scripts/conditions_phase11.py'),
        'admission_sha256':sha256_file(ROOT/'scripts/admission_phase11.py'),
        'cache_helper_sha256':sha256_file(ROOT/'scripts/cache_phase11.py'),
        'case_runner_sha256':{n:sha256_file(ROOT/'scripts'/n) for n in ('benchmark_phase8.py','benchmark_phase2.py')},
        'scope':'Same SDK and 8/2/2/8 pools; full process lifetime includes planning, encode, strict full decode, hash and no-clobber publish. Inclusive waited-descendant CPU controls whole-block background and delivered CPU. Root-only disk/P-share and live within-run CPU are not used as descendant measurements.'}
    target=directory/'report.json'
    report['frozen_sources']=freeze_sources(directory,('workflow_phase11.py','conditions_phase11.py','admission_phase11.py','cache_phase11.py','phase11_common.py','analyze_phase11.py','benchmark_phase8.py','benchmark_phase2.py'))
    def save():write_json(target,report)
    caches=ComparisonCaches({'hd60':source},set().union(*(set(c) for c in closures.values())),directory,report,save)
    def run(label,load,block,attempt,slot,warmup):
        identity=f'hd60-l{load}-{label}-b{block}-a{attempt}-s{slot}';output=directory/(identity+'.mp4');counter=directory/(identity+'.counter.json')
        specification={'operation':'transcode','input':source,'start':60,'duration':60,'output':str(output),
            'encoder':'software','rate_control':'quality','fps':30,'max_width':1920,'max_height':1080,'timeout_seconds':1100,
            'threads':8,'decoder_threads':2,'filter_threads':2,'validation_threads':8}
        request={'package':str(ROOT),'ffmpeg':binaries[label]['ffmpeg'],'ffprobe':binaries[label]['ffprobe'],
            'state':str(directory/(label+'-state')),'spec':specification,'label':label,'trial':block,'warmup':warmup,'matched_progress':True}
        argv=['/usr/bin/env','FFV2_BENCH_IMAGES='+str(image_lists[label]),tools['binary'],str(counter),source,str(load),tools['load_program'],'0',
            str(DEFAULT_POLICY['background_admission_max']),'--',sys.executable,'-B',str(ROOT/'scripts/benchmark_phase8.py'),'--case',json.dumps(request)]
        stdout=directory/(identity+'.stdout.json');stderr=directory/(identity+'.stderr.log')
        watch=watched(argv,stdout,stderr,directory);caches.current.check();data=read(counter);environment=validate_case(data,load,pipeline=True)
        row={'profile':'hd60','load':load,'label':label,'block':block,'attempt':attempt,'slot':slot,'warmup':warmup,
            'counter':str(counter),'counter_sha256':sha256_file(counter),'environment':environment,'watchdog':watch,
            'cache_hold_id':caches.current.record['lease_id']}
        if data['status']=='completed':
            value=read(stdout);receipt=read(value['receipt']);metadata=receipt['validation']['metadata'];tuning=value['runtime_tuning']
            if (value['sha256']!=expected[label] or sha256_file(output)!=expected[label] or int(metadata['video']['nb_frames'])!=1800 or not metadata.get('audio') or
                    tuple(tuning[k] for k in ('encoder_threads','decoder_threads','filter_threads','validation_threads'))!=(8,2,2,8)):
                raise RuntimeError('Complete workflow frame/audio/pool/quality contract failed')
            if data['input_bytes']!=Path(source).stat().st_size or data['image_count']!=len(closures[label]):raise RuntimeError('Conditioned files differ')
            saved=report.setdefault('encoding_argv',{});encoding=receipt['encoding']['argv'][1:-1]
            if encoding!=spec['argv']:raise RuntimeError('Frozen quality argv differs from workflow')
            saved[label]=encoding
            row.update(value,seconds=data['process']['wall_seconds'],warmup=warmup)
        elif data['status']!='environment_rejected':raise RuntimeError('Conditioned workflow measurement failed')
        report['rows'].append(row);save()
        print(json.dumps({'profile':'hd60','load':load,'label':label,'block':block,'seconds':round(row.get('seconds',0),4),
            'valid_environment':environment['valid'],'reasons':environment['reasons']}),flush=True)
        return row
    try:
        save()
        for load in report['load_levels']:
            with caches.hold('hd60',load,-1,-1,warmup=True):
                for slot,label in enumerate(binaries):run(label,load,-1,-1,slot,True)
        for block in range(9 if args.mode=='confirm' else 0):
            for load in ([0,2] if block%2==0 else [2,0]):
                completed=False
                while sum(b['load']==load for b in report['blocks'])<args.max_attempts:
                    attempt=sum(b['load']==load for b in report['blocks'])
                    labels=list(binaries);offset=(attempt+block)%3;labels=labels[offset:]+labels[:offset];rows=[]
                    with caches.hold('hd60',load,block,attempt,warmup=False):
                        for slot,label in enumerate(labels+list(reversed(labels))):
                            row=run(label,load,block,attempt,slot,False);rows.append(row)
                            if not row['environment']['valid']:break
                    validation=validate_block(rows,list(binaries),load,pipeline=True)
                    report['blocks'].append({'profile':'hd60','load':load,'block':block,'attempt':attempt,'validation':validation,'rows':[r['counter'] for r in rows]});save()
                    print(json.dumps({'load':load,'block':block,'attempt':attempt,'validation':validation}),flush=True)
                    if validation['valid']:completed=True;break
                if not completed:
                    report.setdefault('exhausted_groups',[]);key='hd60/load'+str(load)
                    if key not in report['exhausted_groups']:report['exhausted_groups'].append(key)
        if package!={p.name:sha256_file(p) for p in sorted((ROOT/'ffv2').glob('*.py'))}:raise RuntimeError('SDK changed')
        if sha256_file(args.baseline)!=report['baseline']['sha256']:raise RuntimeError('Baseline snapshot changed')
        for label,value in binaries.items():
            if library_closure([Path(value[n]) for n in ('ffmpeg','ffprobe')])!=closures[label]:raise RuntimeError('Runtime changed')
        for name,key in (('workflow_phase11.py','runner_sha256'),('conditions_phase11.py','condition_sha256'),('admission_phase11.py','admission_sha256'),('cache_phase11.py','cache_helper_sha256')):
            if sha256_file(ROOT/'scripts'/name)!=report[key]:raise RuntimeError('Frozen protocol changed')
        for name,checksum in report['case_runner_sha256'].items():
            if sha256_file(ROOT/'scripts'/name)!=checksum:raise RuntimeError('Case runner changed')
        if any(sha256_file(ROOT/'scripts'/name)!=record['sha256'] for name,record in report['frozen_sources'].items()):raise RuntimeError('Frozen measurement source changed')
        if (directory/'admission.jsonl').exists():report['admission_log_sha256']=sha256_file(directory/'admission.jsonl')
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:save()
    if report['status']!='completed':raise RuntimeError(report.get('error','Incomplete workflow'))
    print(json.dumps({'report':str(target)}))


if __name__=='__main__':main()
