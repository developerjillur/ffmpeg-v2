#!/usr/bin/python3 -B
"""Exercise the complete shared cache lease before independent timing."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time
import uuid

from phase11_common import ROOT,WORK,read
from cache_phase11 import HeldCache
from ffv2.config import check_mounts
from ffv2.engine import library_closure
from ffv2.io import sha256_file,write_json
from ffv2.darwin import process_info


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=('hd60','raw30'),default='hd60');args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    prior=read(WORK/'confirm-20261104T111232-f24b2b00/report.json')
    sources={args.profile:prior['sources'][args.profile]}
    for value in sources.values():
        if sha256_file(Path(value['path']))!=value['sha256']:raise RuntimeError('Frozen input changed')
    for label,binary in prior['configurations'].items():
        if library_closure([Path(binary)])!=prior['engine_files'][label]:raise RuntimeError('Frozen engine changed')
    directory=WORK/('cache-calibration-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8]);check_mounts(directory);directory.mkdir(mode=0o700)
    held=HeldCache([v['path'] for v in sources.values()],set().union(*(set(c) for c in prior['engine_files'].values())),directory)
    report={'status':'running','helper_sha256':sha256_file(ROOT/'scripts/cache_phase11.py'),'samples':[]};target=directory/'report.json'
    try:
        report['cache_hold']=held.open();write_json(target,report)
        for _ in range(5):
            held.check();report['samples'].append(process_info(os.getpid()));time.sleep(1)
        report['status']='completed'
    except BaseException as error:report.update(status='failed',error=str(error)[:3000]);raise
    finally:
        report['cache_hold']=held.close(completed=report['status']=='completed');write_json(target,report)
    if report['cache_hold']['status']!='completed':raise RuntimeError('Lease did not retain source/image identity and residency')
    print(json.dumps({'report':str(target),'status':report['status'],'source_bytes':report['cache_hold']['source_bytes'],
        'image_bytes':report['cache_hold']['image_bytes'],'owner_after_lock':report['cache_hold']['owner_after_lock'],
        'owner_after_unlock':report['cache_hold']['owner_after_unlock']}))


if __name__=='__main__':main()
