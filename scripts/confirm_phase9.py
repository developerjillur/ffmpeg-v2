#!/usr/bin/python3 -B
"""Independent balanced complete-workflow control for the frozen 0.6.0 preset."""
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
sys.path.insert(0,str(ROOT))
from ffv2.config import check_mounts
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from analyze_phase9 import paired_blocks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--blocks',type=int,choices=(3,5,9),default=5)
    parser.add_argument('--candidate-package',type=Path)
    args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    work=Path(str(lab_path('ffmpeg-v2-phase9')))
    baseline=work/'baseline'
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=baseline,text=True).strip()!='a8e44c8a725eb20279072654e5f5a35b7e961a8e':
        raise RuntimeError('Frozen 0.6.0 checkout required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=baseline,text=True).strip():
        raise RuntimeError('Frozen package modified')
    old=Path(str(lab_path('ffmpeg-v2-phase8/confirm-20261103T181013-bc270fb1/report.json')))
    previous=json.loads(old.read_text());source=previous['profiles']['bbb-1080']
    if sha256_file(Path(source['input']))!=source['source_sha256']:raise RuntimeError('Reference source changed')
    reference=next(r for r in previous['cases'] if r['profile']=='bbb-1080' and r['label']=='candidate-native')
    selected=selection(verify_hashes=True)
    binaries={'native':selected['binaries'],'stock':{name:'/opt/homebrew/bin/'+name for name in ('ffmpeg','ffprobe')}}
    configurations={label:baseline for label in binaries}
    references={label:reference['sha256'] for label in binaries}
    if args.candidate_package:
        candidate=args.candidate_package.resolve(strict=True)
        calibration=json.loads((work/'lookahead-20261104T042208-f25f86bd/report.json').read_text())
        if calibration['status']!='completed':raise RuntimeError('Completed calibration required')
        candidate_sha=next(r['sha256'] for r in calibration['rows'] if r['profile']=='hd60' and r['variant']=='lookahead1')
        configurations={'baseline-native':baseline,'native':candidate,'stock':candidate}
        references={'baseline-native':reference['sha256'],'native':candidate_sha,'stock':candidate_sha}
    closures={label:library_closure([Path(value['ffmpeg']),Path(value['ffprobe'])]) for label,value in binaries.items()}
    directory=work/('workflow-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory);directory.mkdir(mode=0o700)
    def packages():return {str(root):{p.name:sha256_file(p) for p in (root/'ffv2').glob('*.py')} for root in set(configurations.values())}
    package=packages()
    report={'status':'running','phase':9,'mode':'workflow','blocks':args.blocks,'directory':str(directory),
            'baseline_package':str(baseline),'package_sha256':package,'engine_files':closures,
            'configurations':{label:str(root) for label,root in configurations.items()},'reference_outputs':references,
            'runner_sha256':sha256_file(Path(__file__)),'previous_report':str(old),'previous_sha256':sha256_file(old),
            'source':source,'rows':[],'scope':'Complete frozen 0.6.0 plan/encode/strict full decode/hash/atomic publish. Same pools and legacy progress both sides. Independent from tuning calibration; no optimization promoted from this control.'}
    target=directory/'report.json'
    def run(label,block,slot,warmup):
        identity=label+'-'+str(block)+'-'+str(slot)
        spec={'operation':'transcode','input':source['input'],'start':60,'duration':60,
              'output':str(directory/(identity+'.mp4')),'encoder':'software','rate_control':'quality',
              'fps':30,'max_width':1920,'max_height':1080,'timeout_seconds':1200}
        binary=binaries['native' if label=='baseline-native' else label]
        request={'package':str(configurations[label]),'ffmpeg':binary['ffmpeg'],'ffprobe':binary['ffprobe'],
                 'state':str(directory/(label+'-state')),'spec':spec,'label':label,'trial':block,
                 'warmup':warmup,'matched_progress':True}
        stdout=directory/(identity+'.stdout.json');stderr=directory/(identity+'.stderr.log')
        with stdout.open('xb') as out,stderr.open('xb') as err:
            child=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/benchmark_phase8.py'),'--case',json.dumps(request)],
                                 stdout=out,stderr=err,timeout=1300)
        if child.returncode:raise RuntimeError(stderr.read_text()[-4000:])
        row=json.loads(stdout.read_text());receipt=json.loads(Path(row['receipt']).read_text())
        metadata=receipt['validation']['metadata'];tuning=row['runtime_tuning']
        actual_argv=receipt['encoding']['argv'][1:-1]
        saved=report.setdefault('encoding_argv',{})
        if label in saved and saved[label]!=actual_argv:
            raise RuntimeError('Matched engine tuning changed')
        saved[label]=actual_argv
        if 'native' in saved and 'stock' in saved and saved['native']!=saved['stock']:
            raise RuntimeError('Native/Stock tuning differs')
        if (row['sha256']!=references[label] or sha256_file(Path(row['output']))!=references[label] or
                int(metadata['video']['nb_frames'])!=1800 or not metadata.get('audio') or
                tuple(tuning[k] for k in ('encoder_threads','decoder_threads','filter_threads','validation_threads'))!=(8,2,2,8)):
            raise RuntimeError('Full workflow identity/frame/audio/pool contract failed')
        row.update(profile='hd60',variant='baseline',block=block,slot=slot,seconds=row['total_seconds'],
                   reference_bit_identical=row['sha256']==reference['sha256'])
        report['rows'].append(row);write_json(target,report)
        print(json.dumps({'label':label,'block':block,'seconds':round(row['seconds'],3)}),flush=True)
    try:
        write_json(target,report)
        for slot,label in enumerate(configurations):run(label,-1,slot,True)
        for block in range(args.blocks):
            if args.candidate_package:
                labels=list(configurations);offset=block%len(labels);labels=labels[offset:]+labels[:offset]
                order=labels+list(reversed(labels))
            else:order=('native','stock','stock','native') if block%2 else ('stock','native','native','stock')
            for slot,label in enumerate(order):run(label,block,slot,False)
        if package!=packages():raise RuntimeError('Frozen package changed')
        if sha256_file(Path(source['input']))!=source['source_sha256']:raise RuntimeError('Source changed during confirmation')
        if sha256_file(Path(__file__))!=report['runner_sha256']:raise RuntimeError('Runner changed')
        for label,value in binaries.items():
            if closures[label]!=library_closure([Path(value['ffmpeg']),Path(value['ffprobe'])]):raise RuntimeError('Binary closure changed')
        report['comparison']=paired_blocks([r for r in report['rows'] if r['label'] in ('native','stock')])
        if args.candidate_package:
            report['vs_frozen_native']=paired_blocks([dict(r,label='stock' if r['label']=='baseline-native' else 'native')
                for r in report['rows'] if r['label'] in ('baseline-native','native')])
        report['stage_medians']={label:{key:statistics.median(r[key] for r in report['rows'] if r['label']==label and not r['warmup'])
                                       for key in ('encode_seconds','decode_seconds','planning_seconds','capability_seconds')}
                                 for label in configurations}
        report['status']='completed'
    except BaseException as error:
        report.update(status='failed',error=str(error)[:4000]);raise
    finally:write_json(target,report)
    print(json.dumps({'report':str(target),'comparison':report['comparison']}))


if __name__=='__main__':main()
