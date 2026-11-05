#!/usr/bin/python3 -B
"""নতুন candidate-এর base/extended media proof; successful steps checksum-bound reuse।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.engine import PHASE2_REQUIRED,verify_extended
from ffv2.io import sha256_file,write_json
from ffv2.releases import package_files

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prefix',required=True,type=Path)
    parser.add_argument('--directory',type=Path)
    args=parser.parse_args()
    prefix=args.prefix.resolve(strict=True)
    directory=args.directory or Path(str(lab_path('ffmpeg-v2-phase7')))/('candidate-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/'report.json'
    report=json.loads(path.read_text()) if path.exists() else {'status':'running','install_prefix':str(prefix),'package_files':package_files(),'runs':{}}
    if report['install_prefix']!=str(prefix) or report['package_files']!=package_files():
        raise RuntimeError('Candidate/code changed; retain previous report and use a fresh directory')
    environment={**os.environ,'FFV2_IGNORE_SYSTEM_MEMORY':'1'}
    def step(name,arguments):
        saved=report['runs'].get(name)
        script=ROOT/'scripts'/arguments[0]
        if saved and saved.get('exit_code')==0 and sha256_file(Path(saved['report']))==saved['sha256'] and saved['script_sha256']==sha256_file(script):
            value=json.loads(Path(saved['report']).read_text())
            if value.get('status')=='completed':
                return Path(saved['report'])
        stdout,stderr=directory/(name+'.stdout.json'),directory/(name+'.stderr.log')
        script_before=sha256_file(script)
        with stdout.open('w') as out,stderr.open('w') as err:
            child=subprocess.run([sys.executable,'-B',str(script),*arguments[1:]],cwd=ROOT,env=environment,stdout=out,stderr=err,timeout=1200)
        if sha256_file(script)!=script_before:
            raise RuntimeError('Verification script changed during execution')
        record={'exit_code':child.returncode,'stdout':str(stdout),'stderr':str(stderr),'script_sha256':script_before}
        report['runs'][name]=record
        write_json(path,report)
        if child.returncode:
            raise RuntimeError(name+' failed: '+stderr.read_text()[-6000:])
        output=json.loads(stdout.read_text())
        proof=Path(output['report']) if 'report' in output else Path(output['directory'])/'report.json'
        value=json.loads(proof.read_text())
        if value['status']!='completed' or value['install_prefix']!=str(prefix):
            raise RuntimeError('Completed same-candidate proof missing')
        record.update(report=str(proof),sha256=sha256_file(proof))
        write_json(path,report)
        print(json.dumps({'step':name,'status':'pass','report':str(proof)}),flush=True)
        return proof
    try:
        native_path=step('native',['verify_native_media.py','--prefix',str(prefix)])
        extended_path=step('extended',['verify_phase2.py','--prefix',str(prefix),'--directory',str(directory/'extended'),
            '--natural-proof',str(ROOT/'.runtime/verification/phase2-natural-20261102T175524-d01d544e/report.json')])
        mcp_path=step('mcp',['verify_mcp_pipeline.py','--prefix',str(prefix)])
        native=json.loads(native_path.read_text())
        tests={}
        sources=[]
        for proof in (extended_path,mcp_path):
            value=json.loads(proof.read_text());tests.update(value['tests'])
            sources.append({'path':str(proof),'sha256':sha256_file(proof)})
        if any(tests.get(name,{}).get('status')!='pass' for name in PHASE2_REQUIRED):
            raise RuntimeError('Extended candidate gate is incomplete')
        index={'schema_version':1,'status':'completed','install_prefix':str(prefix),'binary_version':native['binary_version'],
            'tests':tests,'reports':sources,'package_files':package_files(),'scope':'Same candidate base, extended media/GPU/fault/soak and actual stdio MCP; performance remains separate.'}
        index_path=directory/'extended-acceptance.json'
        write_json(index_path,index)
        native['phase2_acceptance']={'path':str(index_path),'sha256':sha256_file(index_path)}
        verify_extended(native,prefix)
        write_json(native_path,native)
        report['runs']['native']['sha256']=sha256_file(native_path)
        report.update(status='completed',native_report=str(native_path),extended_acceptance=str(index_path),extended_checks=len(tests))
    except BaseException as error:
        report.update(status='failed',error=str(error)[:7000])
        raise
    finally:
        write_json(path,report)
    print(json.dumps({'report':str(path),'native_report':str(native_path),'extended_acceptance':str(index_path),'checks':len(tests)}))

if __name__=='__main__':main()
