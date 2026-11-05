#!/usr/bin/python3 -B
"""Actual CLI defaults match accepted target media and retained UHD outputs."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.config import check_mounts
from ffv2.io import sha256_file,write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--analysis',required=True,type=Path)
    parser.add_argument('--launcher',type=Path,default=ROOT/'bin/ffv2')
    args=parser.parse_args()
    analysis=json.loads(args.analysis.read_text())
    if analysis['status']!='completed' or not analysis['release_performance_accepted']:
        raise RuntimeError('Accepted independent Phase 8 analysis required')
    timing=Path(analysis['source_report'])
    quality=Path(analysis['quality_report'])
    if sha256_file(timing)!=analysis['source_sha256'] or sha256_file(quality)!=analysis['quality_sha256']:
        raise RuntimeError('Accepted timing/quality evidence changed')
    current=json.loads(timing.read_text())
    previous_path=Path(str(lab_path('ffmpeg-v2-phase4/acceptance-20261103T170546-0cf42211/report.json')))
    previous=json.loads(previous_path.read_text())
    if previous['status']!='completed':
        raise RuntimeError('Completed unchanged UHD reference required')
    directory=Path(str(lab_path('ffmpeg-v2-phase8')))/('default-cli-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory)
    directory.mkdir(mode=0o700)
    report={'status':'running','launcher':str(args.launcher),'directory':str(directory),'checks':{},
            'evidence':{str(p):sha256_file(p) for p in (args.analysis,timing,quality,previous_path)},
            'contract':'No pool overrides; published SHA equals all-frame quality-approved output.'}
    try:
        for name in ('bbb-1080','tos-liveaction','bbb-2160','bbb-2160-to1080'):
            reference=current if name in current['profiles'] else previous
            profile=reference['profiles'][name]
            row=next(r for r in reference['cases'] if r['profile']==name and r['label']=='candidate-native' and not r['warmup'])
            if sha256_file(Path(profile['input']))!=profile['source_sha256']:
                raise RuntimeError('Reference media changed')
            spec={'operation':'transcode','input':profile['input'],'output':str(directory/(name+'.mp4')),
                  'encoder':'software','rate_control':'quality','fps':profile['fps'],'start':60,'duration':60,
                  'max_width':profile['width'],'max_height':profile['height'],'timeout_seconds':1200}
            spec_path=directory/(name+'.spec.json')
            write_json(spec_path,spec)
            result=subprocess.run([str(args.launcher),'--ignore-system-memory','--state-dir',str(directory/'state'),
                                   'run',str(spec_path)],capture_output=True,text=True,timeout=1300)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout)[-4000:])
            value=json.loads(result.stdout)
            if value['status']!='completed':
                raise RuntimeError(str(value.get('error')))
            receipt=value['receipt']
            plan=json.loads((Path(receipt['directory'])/'plan.json').read_text())
            tuning=plan['runtime_tuning']
            expected=(8,2,2,8) if name in current['profiles'] else (4,2,4 if name=='bbb-2160-to1080' else 2,4)
            actual=tuple(tuning[k] for k in ('encoder_threads','decoder_threads','filter_threads','validation_threads'))
            if actual!=expected or receipt['output_sha256']!=row['sha256'] or sha256_file(Path(value['output']))!=row['sha256']:
                raise RuntimeError('Actual defaults or approved media identity mismatch: '+name)
            report['checks'][name]={'status':'pass','runtime_tuning':tuning,'output_sha256':row['sha256'],
                'runtime_code_id':plan.get('runtime_code_id'),'engine_selection_id':plan['binary'].get('engine_selection_id'),
                'receipt':str(Path(receipt['directory'])/'receipt.json'),'output':value['output']}
            write_json(directory/'report.json',report)
            print(json.dumps({'profile':name,'status':'pass'}),flush=True)
        report['tests']={name:row for name,row in report['checks'].items()}
        report['status']='completed'
    except BaseException as error:
        report.update(status='failed',error=str(error)[:4000]);raise
    finally:
        write_json(directory/'report.json',report)
    print(json.dumps({'report':str(directory/'report.json'),'checks':len(report['checks'])}))


if __name__=='__main__':
    main()
