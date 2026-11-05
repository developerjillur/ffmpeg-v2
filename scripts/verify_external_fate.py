#!/usr/bin/python3 -B
"""Pinned FFmpeg source-এর selected external FATE targets; private QA samples।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
from pathlib import Path
import sys
import time
import uuid
import os
import subprocess

from acquire_phase4_corpus import Guard
from verify_phase2 import Verification
from ffv2.io import capture, sha256_file, write_json, terminate
from ffv2.worker import host_lock, supervised
from ffv2.resources import snapshot

SAMPLES = Path(str(lab_path('ffmpeg-v2-external-fate/samples')))
BASE = 'https://fate-suite.ffmpeg.org/'
TARGETS = {
 'h264-conformance-aud_mw_e':['h264-conformance/AUD_MW_E.264'],
 'hevc-conformance-AMP_A_Samsung_4':['hevc-conformance/AMP_A_Samsung_4.bit'],
 'vp9-2pass-akiyo':['vp9-test-vectors/vp90-2-2pass-akiyo.webm'],
 'vp9p2-20-10bit-yuv420':['vp9-test-vectors/vp92-2-20-10bit-yuv420.webm'],
 'png-rgb48':['png1/lena-rgb48.png'],
 'png-rgba64':['png1/lena-rgba64.png'],
 'webp-rgba-lossless':['webp/rgba_lossless.webp'],
 'webp-rgba-lossy-q80':['webp/rgba_q80.webp'],
 'vorbis-12':['vorbis/mono_small.ogg','vorbis/mono_small.pcm'],
 'opus-testvector01':['opus/testvector01.mka','opus/testvector01.dec'],
 'aac-al04_44':['aac/al04_44.mp4','aac/al04_44.s16'],
 'mp3-float-conf-compl':['mp3-conformance/compl.bit','mp3-conformance/compl.f32'],
 'flac-16-fixed':['audio-reference/luckynight_2ch_44kHz_s16.wav'],
 'matroska-remux':['vp9-test-vectors/vp90-2-2pass-akiyo.webm'],
 'matroska-prores-zlib':['mkv/prores_zlib.mkv'],
}

def secure_ipv4_download(relative, destination, guard, retained):
    if destination.is_file():
        checksum=sha256_file(destination)
        if retained and checksum!=retained['sha256']:
            raise RuntimeError('Previously acquired sample changed: '+relative)
        return {**(retained or {}),'status':'reused','url':BASE+relative,'bytes':destination.stat().st_size,'sha256':checksum}
    nonce=uuid.uuid4().hex[:8]
    part=destination.with_name(destination.name+'.'+nonce+'.part')
    headers=part.with_suffix('.headers')
    log=part.with_suffix('.curl.log')
    maximum=24*1024**2
    guard.check()
    with log.open('xb') as diagnostic:
        child=subprocess.Popen(['/usr/bin/curl','--silent','--show-error','--fail','--ipv4','--http1.1',
            '--proto','=https','--connect-timeout','8','--max-time','120','--max-filesize',str(maximum),
            '--dump-header',str(headers),'--output',str(part),BASE+relative],stdout=diagnostic,stderr=diagnostic,start_new_session=True)
        try:
            while child.poll() is None:
                guard.check()
                if (part.exists() and part.stat().st_size>maximum) or (headers.exists() and headers.stat().st_size>65536) or log.stat().st_size>32768:
                    raise RuntimeError('Transfer/header/log bound exceeded')
                try:child.wait(timeout=.2)
                except subprocess.TimeoutExpired:pass
            if child.returncode:
                raise OSError('Verified HTTPS/IPv4 transfer failed: '+str(child.returncode))
        finally:
            terminate(child)
    fields={}
    status=None
    for line in headers.read_text().splitlines():
        if line.startswith('HTTP/'):
            status=int(line.split()[1]);fields={}
        elif ':' in line:
            key,value=line.split(':',1);fields[key.lower()]=value.strip()
    if status!=200 or not 0<part.stat().st_size<=maximum or int(fields.get('content-length','0'))!=part.stat().st_size:
        raise RuntimeError('Complete publisher HTTPS object/size was not observed')
    with part.open('rb') as stream:os.fsync(stream.fileno())
    checksum=sha256_file(part)
    os.link(part,destination,follow_symlinks=False)
    return {'status':'downloaded','url':BASE+relative,'bytes':part.stat().st_size,'sha256':checksum,
            'etag':fields.get('etag'),'last_modified':fields.get('last-modified'),'tls_verified':True,'transport':'HTTPS IPv4 curl',
            'checksum_scope':'observed HTTPS object, not publisher-signed digest'}

def official_rsync_missing(guard,retained):
    missing=[]
    records={}
    for relative in sorted({p for values in TARGETS.values() for p in values}):
        target=SAMPLES/relative
        if target.is_file():
            checksum=sha256_file(target)
            if retained.get(relative) and checksum!=retained[relative]['sha256']:
                raise RuntimeError('Retained sample changed')
            records[relative]={**retained.get(relative,{}),'status':'reused','bytes':target.stat().st_size,'sha256':checksum}
        else:
            missing.append(relative)
    if not missing:
        return records
    stage=SAMPLES.parent/('rsync-'+uuid.uuid4().hex)
    stage.mkdir(mode=0o700)
    listing=stage/'selected-files.txt'
    listing.write_text('\n'.join(missing)+'\n')
    print(json.dumps({'new_sample_paths':[str(SAMPLES/p) for p in missing],'transfer_stage':str(stage)}),flush=True)
    log=stage/'transfer.log'
    with log.open('xb') as diagnostic:
        child=subprocess.Popen(['/usr/bin/rsync','-rt','--safe-links','--partial','--max-size=25165824','--contimeout=8','--timeout=20',
            '--files-from='+str(listing),'rsync://fate-suite.ffmpeg.org/fate-suite/',str(stage/'payload')+'/'],
            stdout=diagnostic,stderr=diagnostic,start_new_session=True)
        deadline=time.monotonic()+360
        try:
            while child.poll() is None:
                guard.check()
                if time.monotonic()>deadline or log.stat().st_size>65536 or sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())>128*1024**2:
                    raise RuntimeError('Bounded rsync transfer time/storage/log limit exceeded')
                try:child.wait(timeout=.2)
                except subprocess.TimeoutExpired:pass
            if child.returncode:
                raise OSError('Official bounded rsync transfer failed: '+str(child.returncode)+' '+log.read_text()[-1000:])
        finally:
            terminate(child)
    for relative in missing:
        source=stage/'payload'/relative
        if source.is_symlink() or not source.is_file() or not 0<source.stat().st_size<=24*1024**2:
            raise RuntimeError('Selected upstream file missing/oversize/nonregular: '+relative)
        records[relative]={'status':'downloaded','url':'rsync://fate-suite.ffmpeg.org/fate-suite/'+relative,
            'sha256':sha256_file(source),'bytes':source.stat().st_size,'transport':'official upstream rsync',
            'checksum_scope':'observed local SHA256 plus rsync transfer checks; no TLS or publisher-signed digest claimed'}
    write_json(stage/'transfer.json',{'status':'completed','files':records,'log_sha256':sha256_file(log)})
    for relative in missing:
        target=SAMPLES/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        os.link(stage/'payload'/relative,target,follow_symlinks=False)
    return records

def acquire(transport):
    SAMPLES.mkdir(parents=True,exist_ok=True)
    guard=Guard(SAMPLES)
    receipt=SAMPLES.parent/'acquisition.json'
    retained=json.loads(receipt.read_text()).get('files',{}) if receipt.exists() else {}
    if receipt.exists():
        os.link(receipt,receipt.with_name('acquisition-'+uuid.uuid4().hex+'.previous.json'),follow_symlinks=False)
    report={'status':'running','base_url':BASE,'files':{},'maximum_total_bytes':128*1024**2,
        'provenance':'https://ffmpeg.org/fate.html','scope':'Selected official regression samples; private QA only, no blanket redistribution licence asserted; observed HTTPS SHA256, not signed publisher checksums.'}
    try:
        rsync_records=official_rsync_missing(guard,retained) if transport=='rsync' else {}
        for relative in sorted({p for values in TARGETS.values() for p in values}):
            destination=SAMPLES/relative
            destination.parent.mkdir(parents=True,exist_ok=True)
            for attempt in range(3):
                try:
                    value=rsync_records[relative] if transport=='rsync' else secure_ipv4_download(relative,destination,guard,retained.get(relative))
                    break
                except (OSError,ValueError) as error:
                    if attempt==2:
                        raise
                    time.sleep(.5)
            report['files'][relative]=value
            if sum(item['bytes'] for item in report['files'].values())>report['maximum_total_bytes']:
                raise RuntimeError('External sample total budget exceeded')
            write_json(receipt,report)
            print(json.dumps({'sample':relative,'bytes':value['bytes']}),flush=True)
        report['status']='completed'
    except BaseException as error:
        report.update(status='failed',error=str(error)[:3000])
        raise
    finally:
        write_json(receipt,report)
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prefix',type=Path)
    parser.add_argument('--acquire-only',action='store_true')
    parser.add_argument('--run-only',action='store_true')
    parser.add_argument('--transport',choices=('rsync','https'),default='rsync')
    args=parser.parse_args()
    acquisition=json.loads((SAMPLES.parent/'acquisition.json').read_text()) if args.run_only else acquire(args.transport)
    if args.acquire_only:
        return 0
    if not args.prefix or acquisition['status']!='completed':
        raise RuntimeError('Completed acquisition and candidate prefix required')
    for relative,record in acquisition['files'].items():
        if sha256_file(SAMPLES/relative)!=record['sha256']:
            raise RuntimeError('Retained external sample changed: '+relative)
    prefix=args.prefix.resolve(strict=True)
    build=prefix.parent/'build'
    directory=SAMPLES.parent/('run-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    verify=Verification(prefix,directory)
    code,out,err=capture(['/usr/bin/make','-s','--no-print-directory','-C',str(build),'fate-list','SAMPLES='+str(SAMPLES)],timeout=30,env={**__import__('os').environ,'LC_ALL':'C'},limit=1024**2)
    if code:
        raise RuntimeError(err[-2000:])
    enabled=out.splitlines()
    missing=[name for name in TARGETS if name not in enabled and 'fate-'+name not in enabled]
    if missing:
        raise RuntimeError('Selected targets are not enabled: '+str(missing))
    verify.report.update(selected_targets=list(TARGETS),enabled_target_count=len(enabled),enabled_list_sha256=__import__('hashlib').sha256(out.encode()).hexdigest(),
        acquisition={'path':str(SAMPLES.parent/'acquisition.json'),'sha256':sha256_file(SAMPLES.parent/'acquisition.json')},
        scope='15 selected enabled external-sample targets only; full external suite was not downloaded or run.')
    plan={'kind':'diagnostic','spec':{'operation':'external-fate','output':str(directory/'external-fate.json')},
          'estimates':{'job_memory_bytes':2*1024**3,'output_budget_bytes':2*1024**3},'timeout_seconds':900}
    from ffv2.io import digest
    plan['plan_id']=digest(plan)
    queued=verify.store.enqueue(plan);job=verify.store.claim(queued['id'])
    attempt=verify.store.root/'jobs'/job['id']/'attempt-001';attempt.mkdir(parents=True)
    try:
        with host_lock(verify.settings) as lock_fd:
            receipt=supervised(['/usr/bin/make','-j2','SAMPLES='+str(SAMPLES),*('fate-'+name for name in TARGETS)],
                'external-fate',job,attempt,verify.settings,snapshot(directory),lock_fd,build/'tests/data',
                cwd=build,process_kind='build',environment={'LC_ALL':'C','SAMPLES':str(SAMPLES),'FATE_SAMPLES':str(SAMPLES)})
        verify.store.update(job['id'],'completed',receipt=receipt)
        for name in TARGETS:
            path=build/'tests/data/fate'/(name+'.rep')
            if not path.is_file() or path.read_text().split(':')[1]!='0':
                raise RuntimeError('FATE target record failed/missing: '+name)
            verify.report['tests'][name]={'status':'pass','record':str(path),'sha256':sha256_file(path),'samples':TARGETS[name]}
        verify.report.update(status='completed',receipt=receipt)
    except BaseException as error:
        verify.store.update(job['id'],'failed')
        verify.report.update(status='failed',error=str(error)[:6000])
        raise
    finally:
        verify.save()
    print(json.dumps({'report':str(directory/'report.json'),'passed':len(verify.report['tests']),'enabled':len(enabled)}))
    return 0

if __name__=='__main__':raise SystemExit(main())
