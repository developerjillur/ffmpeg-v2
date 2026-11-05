#!/usr/bin/python3 -B
"""দুই installed Python runtime-এর actual regression logs ও counts সংরক্ষণ।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.io import write_json,sha256_file
from ffv2.releases import package_files

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work-root',type=Path,default=Path(str(lab_path('ffmpeg-v2-phase7'))))
    args=parser.parse_args()
    directory=args.work_root/('unit-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(parents=True)
    environment=os.environ.copy()
    inherited_waiver=environment.pop('FFV2_IGNORE_SYSTEM_MEMORY',None) is not None
    report={'status':'running','package_files':package_files(),'runs':[],
            'test_policy':'Default-policy controls tested without task memory waiver; media jobs retain their explicit scoped waiver',
            'inherited_memory_waiver_removed':inherited_waiver}
    try:
        for index,program in enumerate(('/usr/bin/python3','/opt/homebrew/bin/python3')):
            version=subprocess.check_output([program,'--version'],text=True).strip()
            log=directory/('python-'+str(index)+'.log')
            with log.open('xb') as stream:
                result=subprocess.run([program,'-B','-W','error::ResourceWarning','-m','unittest','discover','-s','tests','-q'],cwd=ROOT,env=environment,stdout=stream,stderr=stream,timeout=60)
            content=log.read_text()
            matched=re.search(r'Ran (\d+) tests.*?\n\nOK',content,re.S)
            if result.returncode or not matched or 'ResourceWarning' in content:
                raise RuntimeError(version+' regression failure: '+content[-5000:])
            report['runs'].append({'version':version,'tests':int(matched.group(1)),'exit_code':result.returncode,'log':str(log),'sha256':sha256_file(log)})
        if package_files()!=report['package_files']:
            raise RuntimeError('Code changed during regression matrix')
        report['status']='completed'
    except BaseException as error:
        report.update(status='failed',error=str(error)[:6000])
        raise
    finally:
        write_json(directory/'report.json',report)
    print(json.dumps({'report':str(directory/'report.json'),'runs':report['runs']}))

if __name__=='__main__':main()
