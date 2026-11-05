#!/usr/bin/python3 -B
"""Balanced matched-argv media runs with kernel CPU, instructions and I/O."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import random
import re
import statistics
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.config import check_mounts
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from ffv2.resources import Policy,snapshot
from verify_phase2 import Verification

WORK=Path(str(lab_path('ffmpeg-v2-phase9')))
OLD=Path(str(lab_path('ffmpeg-v2-phase8')))


def read(path): return json.loads(Path(path).read_text())


def counters(text):
    result={}
    for line in text.splitlines():
        match=re.fullmatch(r'\s*(real|user|sys)\s+([\d.]+)\s*',line)
        if match:
            result[match[1]+'_seconds']=float(match[2]);continue
        match=re.fullmatch(r'\s*(\d+)\s+([a-z ]+)\s*',line)
        if match: result[match[2].strip().replace(' ','_')]=int(match[1])
    if not {'real_seconds','user_seconds','sys_seconds','instructions_retired','cycles_elapsed'}<=result.keys():
        raise RuntimeError('Kernel time/resource counters missing')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=('reproduce','filters','probe','io','queue','lookahead'),default='reproduce')
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--profile',choices=('hd60','raw30'))
    parser.add_argument('--blocks',type=int,choices=(2,3,4,6,8),default=4)
    args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    selected=selection(verify_hashes=True)
    previous=read(OLD/'confirm-20261103T181013-bc270fb1/report.json')
    isolation=read(OLD/'isolation-20261103T182305-6a8a3972/isolation.json')
    hd=next(r for r in previous['cases'] if r['profile']=='bbb-1080' and r['label']=='candidate-native')
    raw=next(r for r in isolation['rows'] if r['mode']=='raw_x264' and r['label']=='native')
    specifications={'hd60':{'argv':read(hd['receipt'])['encoding']['argv'][1:-1],'frames':1800,'reference_sha256':hd['sha256']},
                    'raw30':{'argv':read(raw['receipt'])['argv'][1:-1],'frames':900,'reference_sha256':raw['output_sha256']}}
    if args.mode=='io': specifications={'raw30':specifications['raw30']}
    if args.profile: specifications={args.profile:specifications[args.profile]}
    variants={'reproduce':('baseline',),'filters':('baseline','no_scale'),'probe':('baseline','no_probe'),
              'io':('baseline','direct','no_probe','direct_no_probe'),
              'queue':('queue2','queue4','queue8','queue16'),
              'lookahead':('baseline','lookahead1','synchronous')}[args.mode]
    sources={Path(previous['profiles']['bbb-1080']['input']):previous['profiles']['bbb-1080']['source_sha256'],
             Path(isolation['raw']['path']):isolation['raw']['sha256']}
    for path,checksum in sources.items():
        if sha256_file(path)!=checksum: raise RuntimeError('Retained source changed')
    directory=WORK/(args.mode+'-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory);directory.mkdir(mode=0o700)
    reasons=Policy().admission(snapshot(directory),2*1024**3,4*1024**3)
    if reasons: raise RuntimeError(str(reasons))
    verify=Verification(Path(selected['install_prefix']),directory)
    binaries={'native':selected['binaries']['ffmpeg'],'stock':'/opt/homebrew/bin/ffmpeg'}
    if args.mode=='queue':
        if not args.candidate:raise RuntimeError('Explicit diagnostic candidate required')
        binaries['native']=str(args.candidate.resolve(strict=True))
    candidate_files=library_closure([Path(binaries['native'])])
    report={'status':'running','mode':args.mode,'directory':str(directory),'blocks':args.blocks,'variants':variants,
        'specifications':specifications,'sources':{str(p):h for p,h in sources.items()},'rows':[],'summary':{},'comparisons':{},
        'engine_selection_id':selected['selection_id'],'engine_files':selected['files'],'candidate_files':candidate_files,
        'stock_files':library_closure([Path(binaries['stock']),Path('/opt/homebrew/bin/ffprobe')]),
        'time_tool':{'path':'/usr/bin/time','sha256':sha256_file(Path('/usr/bin/time'))},
        'initial_resources':snapshot(directory).json(),'nice':os.getpriority(os.PRIO_PROCESS,0),
        'python_executable':sys.executable,'python_version':sys.version,'script_sha256':sha256_file(Path(__file__)),
        'scope':'Existing exact Phase 8 argv; time -lp on both engines; balanced adjacent ABBA/BAAB blocks. First two-engine warmup excluded; every slow run retained. Diagnostic encoding stage, not complete workflow.'}
    path=directory/'report.json'
    def save(): write_json(path,report)
    def run(profile,variant,label,block,slot,warmup):
        identity=profile+'-'+variant+'-'+label+'-'+str(block)+'-'+str(slot)
        output=directory/(identity+'.mp4')
        media=list(specifications[profile]['argv'])
        if variant.startswith('queue') and label=='native':
            media[:0]=['-frame_queue_size',variant[5:]]
        if variant in ('lookahead1','synchronous'):
            media+=['-x264-params','lookahead-threads=1'+(':sync-lookahead=0' if variant=='synchronous' else '')]
        if variant=='no_scale':
            pos=media.index('-vf')+1
            if media[pos]!='scale=1920:1080,setsar=1':raise RuntimeError('Identity filter graph required')
            media[pos]='setsar=1'
        if variant in ('direct','direct_no_probe'):
            pos=media.index('-i');media[pos:pos]=['-avioflags','direct']
        if variant in ('no_probe','direct_no_probe'):
            pos=media.index('-i');media[pos:pos]=['-nofind_stream_info']
        receipt=verify.aux(identity,['/usr/bin/time','-lp',binaries[label],*media,str(output)],output,timeout=1200,budget=256*1024**2)
        if int(receipt['last_progress']['frame'])!=specifications[profile]['frames']:
            raise RuntimeError('Full frame coverage mismatch')
        counts=counters(receipt['stderr_tail'])
        row={'profile':profile,'variant':variant,'label':label,'block':block,'slot':slot,'warmup':warmup,
            'seconds':receipt['wall_seconds'],'counters':counts,'output':str(output),'sha256':sha256_file(output),
            'bytes':output.stat().st_size,'peak_job_memory_bytes':receipt['peak_job_memory_bytes'],
            'receipt':str(next(directory.glob(identity+'-*.diagnostic.json'))),
            'load_after':os.getloadavg(),'reference_bit_identical':sha256_file(output)==specifications[profile]['reference_sha256']}
        report['rows'].append(row);save()
        print(json.dumps({'profile':profile,'variant':variant,'engine':label,'block':block,'seconds':round(row['seconds'],3),
                          'cpu':round(counts['user_seconds']+counts['sys_seconds'],2),'instructions':counts['instructions_retired']}),flush=True)
    try:
        save()
        for profile in specifications:
            for variant in variants:
                for slot,label in enumerate(('native','stock')):run(profile,variant,label,-1,slot,True)
        rng=random.Random(202611049)
        for block in range(args.blocks):
            groups=[(p,v) for p in specifications for v in variants];rng.shuffle(groups)
            for index,(profile,variant) in enumerate(groups):
                order=('native','stock','stock','native') if (block+index)%2 else ('stock','native','native','stock')
                for slot,label in enumerate(order):run(profile,variant,label,block,slot,False)
        for profile in specifications:
            for variant in variants:
                grouped={label:[r for r in report['rows'] if r['profile']==profile and r['variant']==variant and r['label']==label and not r['warmup']] for label in binaries}
                hashes={r['sha256'] for label in grouped for r in grouped[label]}
                if len(hashes)!=1:raise RuntimeError('Matched engine/configuration output files differ')
                for label,rows in grouped.items():
                    report['summary'][profile+'/'+variant+'/'+label]={'n':len(rows),'seconds':statistics.median(r['seconds'] for r in rows),
                        'counters':{key:statistics.median(r['counters'][key] for r in rows) for key in rows[0]['counters']},
                        'reference_bit_identical':all(r['reference_bit_identical'] for r in rows)}
                a=report['summary'][profile+'/'+variant+'/native'];b=report['summary'][profile+'/'+variant+'/stock']
                report['comparisons'][profile+'/'+variant]={'native_stock_time_ratio':a['seconds']/b['seconds'],
                    'instructions_ratio':a['counters']['instructions_retired']/b['counters']['instructions_retired'],
                    'cycles_ratio':a['counters']['cycles_elapsed']/b['counters']['cycles_elapsed'],
                    'cpu_seconds_ratio':(a['counters']['user_seconds']+a['counters']['sys_seconds'])/(b['counters']['user_seconds']+b['counters']['sys_seconds'])}
        if sha256_file(Path(__file__))!=report['script_sha256']:raise RuntimeError('Runner changed during measurement')
        selection(verify_hashes=True)
        if library_closure([Path(binaries['native'])])!=candidate_files:raise RuntimeError('Candidate changed during measurement')
        report['status']='completed';save()
    except BaseException as error:
        report.update(status='failed',error=str(error)[:4000]);save();raise
    print(json.dumps({'report':str(path),'comparisons':report['comparisons']}))


if __name__=='__main__':main()
