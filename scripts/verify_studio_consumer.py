#!/usr/bin/python3 -B
"""Existing Studio timeline worker-এ pinned native CLI ও retained-part recovery।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

from verify_phase5 import Check
from ffv2 import engine
from ffv2.config import Settings
from ffv2.errors import FFV2Error
from ffv2.io import sha256_file, write_json
from ffv2.media import probe_path
from ffv2.runtime import run

ROOT=Path(__file__).resolve().parents[1]
STUDIO=ROOT.parent/'higgsfield setup'
WORK=Path(str(lab_path('ffmpeg-v2-phase7')))
DEFAULT_REPORT=Path(str(lab_path('ffmpeg-v2-phase4/default-cli-20261103T093520-224a8c7d/report.json')))

def copy_new(source,destination,maximum=64*1024**2):
    if not source.is_file() or source.stat().st_size>maximum:
        raise RuntimeError('Consumer fixture copy exceeds declared bound')
    with source.open('rb') as incoming,destination.open('xb') as output:
        shutil.copyfileobj(incoming,output,length=256*1024)
        output.flush()
        os.fsync(output.fileno())
    destination.chmod(0o600)
    if sha256_file(destination)!=sha256_file(source):
        raise RuntimeError('Consumer import copy checksum mismatch')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prefix',required=True,type=Path)
    parser.add_argument('--launcher', type=Path)
    parser.add_argument('--assets-root', type=Path)
    parser.add_argument('--work-root', type=Path, default=WORK)
    args=parser.parse_args()
    prefix=args.prefix.resolve(strict=True)
    selected=engine.selection(verify_hashes=True)
    if not selected or Path(selected['install_prefix'])!=prefix:
        raise RuntimeError('Activate the fully verified candidate before real consumer acceptance')
    directory=args.work_root/('studio-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    verify=Check(prefix,directory)
    consumer_root=STUDIO/'data'/('ffv2-acceptance-'+uuid.uuid4().hex)
    print(json.dumps({'affected_new_directory':str(consumer_root),'source_copies':[] if args.assets_root else ['bbb-1080','tos-liveaction'],
                      'reused_source_root':str(args.assets_root) if args.assets_root else None}),flush=True)
    consumer_root.mkdir(mode=0o700)
    scripts=[STUDIO/'scripts/timeline_worker.py',STUDIO/'studio/timeline.py',STUDIO/'studio/storage.py']
    fingerprints={str(p):sha256_file(p) for p in scripts}
    verify.report.update(consumer='Existing Nexa Studio timeline_worker.py',consumer_sources=fingerprints,
                         code_edited=False,consumer_root=str(consumer_root),engine_selection_id=selected['selection_id'],
                         launcher=str(args.launcher) if args.launcher else None)
    sys.path.insert(0,str(STUDIO))
    from studio.timeline import prepare
    try:
        proof=json.loads(DEFAULT_REPORT.read_text())
        if proof['status']!='completed':
            raise RuntimeError('Completed real source derivative receipt required')
        assets={}
        for name in ('bbb-1080','tos-liveaction'):
            record=proof['checks'][name]
            source=Path(record['output'])
            if sha256_file(source)!=record['output_sha256']:
                raise RuntimeError('Real source derivative changed')
            target=(args.assets_root/(name+'.mp4')).resolve(strict=True) if args.assets_root else consumer_root/(name+'.mp4')
            if args.assets_root:
                if sha256_file(target)!=record['output_sha256']:
                    raise RuntimeError('Retained consumer source checksum changed')
            else:
                copy_new(source,target)
            metadata=probe_path(target,verify.caps['ffprobe'])
            identity=uuid.uuid4().hex
            assets[identity]={'id':identity,'name':name,'type':'video','probe':{'format':metadata['format'],'streams':metadata['streams']},
                'sha256':sha256_file(target),'bytes':target.stat().st_size,'path':str(target)}
        ids=list(assets)
        params={'video_references':[{'asset_id':i} for i in ids], 'fps':30,'resolution':'480p','aspect_ratio':'16:9',
            'transition':'fade','transition_duration':.2,'keep_source_audio':True,
            'clips':[{'asset_id':ids[0],'start':1,'end':3,'speed':1,'gain':.8},
                     {'asset_id':ids[1],'start':2,'end':4,'speed':1.25,'gain':.8}]}
        manifest=prepare(params,assets,lambda identity:assets[identity]['path'])
        first=consumer_root/'first';first.mkdir()
        write_json(first/'timeline-request.json',manifest)
        settings=Settings.load(state=directory/'consumer-state')
        def execute_consumer(area, timeout):
            program=['python3',str(STUDIO/'scripts/timeline_worker.py'),str(area)]
            if not args.launcher:
                return run(settings,program,area,timeout=timeout)
            command=[str(args.launcher),'--ignore-system-memory','--state-dir',str(settings.state),'exec',
                     '--work-dir',str(area),'--timeout',str(timeout),'--',*program]
            result=subprocess.run(command,capture_output=True,text=True,timeout=timeout+45)
            write_json(directory/(area.name+'-installed-cli.json'),{'argv':command,'exit_code':result.returncode,
                'stdout':result.stdout[-100000:],'stderr':result.stderr[-12000:]})
            if result.returncode:
                error=json.loads(result.stderr)['error']
                raise FFV2Error(error['code'],error['message'],details=error.get('details'),retryable=error.get('retryable',False),exit_code=result.returncode)
            return json.loads(result.stdout)
        result=execute_consumer(first,180)
        report=json.loads((first/'timeline-result.json').read_text())
        if report['sha256']!=sha256_file(first/'result.mp4') or report['reused_parts'] or report['generation_model_calls']!=0:
            raise RuntimeError('Actual Studio export receipt mismatch')
        checked=verify.media('consumer-full-validation',{'operation':'remux','input':str(first/'result.mp4'),'output':str(directory/'verified.mkv')})
        frames=int(checked['receipt']['validation']['full_decode']['last_progress']['frame'])
        if frames!=manifest['frames']:
            raise RuntimeError('Studio actual final frame count mismatch')
        verify.passed('studio_real_timeline',frames=frames,duration=manifest['duration'],consumer_job_id=result['job_id'],
            output_sha256=report['sha256'],render_accepted_by_owner=report['accepted'],scope='Technical local integration, not creative approval or UI deployment')
        retry=consumer_root/'retry';retry.mkdir()
        write_json(retry/'timeline-request.json',manifest)
        for clip in manifest['clips']:
            for suffix in ('.mp4','.json'):
                name='part-'+str(clip['number'])+suffix
                os.link(first/name,retry/name,follow_symlinks=False)
        second=execute_consumer(retry,180)
        recovered=json.loads((retry/'timeline-result.json').read_text())
        if recovered['reused_parts']!=[c['number'] for c in manifest['clips']] or recovered['sha256']!=report['sha256']:
            raise RuntimeError('Existing consumer part recovery/output equality failed')
        verify.passed('studio_retained_part_recovery',reused_parts=recovered['reused_parts'],output_sha256=recovered['sha256'],consumer_job_id=second['job_id'])
        bad=consumer_root/'tampered';bad.mkdir()
        write_json(bad/'timeline-request.json',{**manifest,'sha256':'0'*64})
        try:
            execute_consumer(bad,30)
        except FFV2Error as error:
            if error.code!='upstream_process_failed' or (bad/'result.mp4').exists():
                raise
            verify.passed('studio_tampered_request_refusal',code=error.code,published=False)
        else:
            raise RuntimeError('Tampered Studio manifest was accepted')
        if {str(p):sha256_file(p) for p in scripts}!=fingerprints:
            raise RuntimeError('Existing consumer source changed during integration')
        verify.report['status']='completed'
    except BaseException as error:
        verify.report.update(status='failed',error=str(error)[:6000])
        raise
    finally:
        verify.save()
    print(json.dumps({'report':str(directory/'report.json'),'checks':len(verify.report['tests']),'consumer_root':str(consumer_root)}))

if __name__=='__main__':main()
