#!/usr/bin/python3 -B
"""Independent matched HD workflow including strict decode, hashing and publish."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase10')))
sys.path.insert(0,str(ROOT))
from ffv2.config import check_mounts
from ffv2.engine import library_closure,selection
from ffv2.io import sha256_file,write_json
from analyze_phase10 import compare


def read(path):return json.loads(Path(path).read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--blocks',type=int,choices=(3,5,7,9),default=7)
    parser.add_argument('--candidate-key',choices=('opt','m4safe','row','rowvec'),default='rowvec')
    args=parser.parse_args();os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    selected=selection(verify_hashes=True);stage=read(WORK/'staged-engines.json')[args.candidate_key]
    quality_path=WORK/'smoke-candidate-20261104T063905-c831595d/quality.json';quality=read(quality_path)
    benchmark=read(quality['source_report'])
    if quality['status']!='completed' or not quality['comparisons']['hd60/candidate']['quality_accepted'] or sha256_file(Path(quality['source_report']))!=quality['source_sha256']:
        raise RuntimeError('Quality-verified candidate required')
    if benchmark['configurations']['candidate']!=stage['binaries']['ffmpeg']:raise RuntimeError('Candidate quality belongs to a different engine')
    old=read(Path(str(lab_path('ffmpeg-v2-phase8/confirm-20261103T181013-bc270fb1/report.json'))))
    source=old['profiles']['bbb-1080']
    if sha256_file(Path(source['input']))!=source['source_sha256']:raise RuntimeError('Input identity failed')
    baseline=Path(str(lab_path('ffmpeg-v2-phase9/baseline')))
    package={p.name:sha256_file(p) for p in sorted((baseline/'ffv2').glob('*.py'))}
    if package!={p.name:sha256_file(p) for p in sorted((ROOT/'ffv2').glob('*.py'))}:raise RuntimeError('Matched frozen 0.6 SDK required')
    binaries={'original':selected['binaries'],'candidate':stage['binaries'],
              'stock':{name:'/opt/homebrew/bin/'+name for name in ('ffmpeg','ffprobe')}}
    closures={label:library_closure([Path(value[n]) for n in ('ffmpeg','ffprobe')]) for label,value in binaries.items()}
    expected={label:next(row['sha256'] for row in benchmark['rows'] if row['profile']=='hd60' and row['label']==label) for label in binaries}
    directory=WORK/('workflow-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory);directory.mkdir(mode=0o700)
    target=directory/'report.json'
    report={'status':'running','phase':10,'mode':'workflow','blocks':args.blocks,'install_prefix':stage['prefix'],
            'package_source_sha256':package,'package':str(baseline),'engine_files':closures,
            'quality_report':str(quality_path),'quality_sha256':sha256_file(quality_path),
            'runner_sha256':sha256_file(Path(__file__)),'case_runner_sha256':{name:sha256_file(ROOT/'scripts'/name) for name in ('benchmark_phase8.py','benchmark_phase2.py')},
            'source':source,'rows':[],'scope':'Frozen SDK; same 8/2/2/8 pools and progress contract. Full planning, encode, strict decode, hash, no-clobber publish. No added synthetic load; unrelated host activity remains.'}
    def save():write_json(target,report)
    def run(label,block,slot,warmup):
        identity=f'{label}-{block}-{slot}';output=directory/(identity+'.mp4')
        spec={'operation':'transcode','input':source['input'],'start':60,'duration':60,'output':str(output),
              'encoder':'software','rate_control':'quality','fps':30,'max_width':1920,'max_height':1080,'timeout_seconds':1200}
        request={'package':str(baseline),'ffmpeg':binaries[label]['ffmpeg'],'ffprobe':binaries[label]['ffprobe'],
                 'state':str(directory/(label+'-state')),'spec':spec,'label':label,'trial':block,'warmup':warmup,'matched_progress':True}
        stdout=directory/(identity+'.stdout.json');stderr=directory/(identity+'.stderr.log')
        with stdout.open('xb') as out,stderr.open('xb') as err:
            completed=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/benchmark_phase8.py'),'--case',json.dumps(request)],stdout=out,stderr=err,timeout=1300)
        if completed.returncode:raise RuntimeError(stderr.read_text()[-4000:])
        row=read(stdout);receipt=read(row['receipt']);metadata=receipt['validation']['metadata'];tuning=row['runtime_tuning']
        if (row['sha256']!=expected[label] or sha256_file(output)!=expected[label] or
                int(metadata['video']['nb_frames'])!=1800 or not metadata.get('audio') or
                tuple(tuning[k] for k in ('encoder_threads','decoder_threads','filter_threads','validation_threads'))!=(8,2,2,8)):
            raise RuntimeError('Workflow source/frame/audio/pool/quality contract failed')
        argv=receipt['encoding']['argv'][1:-1];saved=report.setdefault('encoding_argv',{})
        if saved and argv!=next(iter(saved.values())):raise RuntimeError('Encoding argv differ')
        saved[label]=argv
        row.update(profile='hd60',block=block,slot=slot,seconds=row['total_seconds'],warmup=warmup)
        report['rows'].append(row);save()
        print(json.dumps({'label':label,'block':block,'seconds':round(row['seconds'],3),'encode_seconds':row['encode_seconds'],'decode_seconds':row['decode_seconds']}),flush=True)
    try:
        save()
        for slot,label in enumerate(binaries):run(label,-1,slot,True)
        for block in range(args.blocks):
            labels=list(binaries);offset=block%len(labels);labels=labels[offset:]+labels[:offset]
            for slot,label in enumerate(labels+list(reversed(labels))):run(label,block,slot,False)
        if package!={p.name:sha256_file(p) for p in (baseline/'ffv2').glob('*.py')} or sha256_file(Path(__file__))!=report['runner_sha256']:
            raise RuntimeError('Frozen package/runner changed')
        for label,value in binaries.items():
            if closures[label]!=library_closure([Path(value[n]) for n in ('ffmpeg','ffprobe')]):raise RuntimeError('Engine closure changed')
        for name,checksum in report['case_runner_sha256'].items():
            if sha256_file(ROOT/'scripts'/name)!=checksum:raise RuntimeError('Workflow case runner changed')
        report['comparisons']={label:compare(report['rows'],label) for label in ('original','stock')}
        report['stage_medians']={label:{key:statistics.median(r[key] for r in report['rows'] if r['label']==label and not r['warmup'])
            for key in ('total_seconds','encode_seconds','decode_seconds','planning_seconds','capability_seconds')} for label in binaries}
        report['hd_workflow_improvement_accepted']=report['comparisons']['original']['improvement_accepted'] and report['comparisons']['stock']['stock_gap_closed']
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);raise
    finally:save()
    print(json.dumps({'report':str(target),'comparisons':report['comparisons']}))


if __name__=='__main__':main()
