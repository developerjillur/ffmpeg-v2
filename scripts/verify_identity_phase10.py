#!/usr/bin/python3 -B
"""Strict full decode and per-frame video/audio SHA-256 identity controls."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path);args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    report=json.loads(args.report.read_text());target=args.report.with_name('decoded-identity.json')
    if report['status']!='completed' or target.exists():raise RuntimeError('Completed encodes and fresh identity destination required')
    directory=args.report.parent/'decoded-identity';directory.mkdir(mode=0o700)
    selected=selection(verify_hashes=True);verify=Verification(Path(selected['install_prefix']),directory/'guarded')
    result={'status':'running','source_report':str(args.report),'source_sha256':sha256_file(args.report),
            'tests':{},'decodes':{},'scope':'All output video frames, and all decoded PCM audio frames when present, must have identical timestamps, sizes and SHA-256 across engines. Container/version metadata may differ.'}
    try:
        for profile,spec in report['specifications'].items():
            decoded={}
            for label in report['configurations']:
                row=next(r for r in report['rows'] if r['profile']==profile and r['label']==label)
                if sha256_file(Path(row['output']))!=row['sha256']:raise RuntimeError('Encoded source changed')
                if row['sha256'] not in decoded:
                    frames=directory/(profile+'-'+label+'.framehash')
                    verify.aux(profile+'-'+label,[selected['binaries']['ffmpeg'],'-v','error','-nostdin','-n','-xerror','-err_detect','explode',
                        '-threads','8','-i',row['output'],'-map','0:v:0','-map','0:a:0?','-c:v','rawvideo','-threads:v','1',
                        '-pix_fmt','yuv420p','-c:a','pcm_s16le','-threads:a','1','-f','framehash','-hash','sha256',str(frames)],frames,timeout=300,budget=16*1024**2)
                    lines=[line for line in frames.read_text().splitlines() if line and not line.startswith('#')]
                    counts={stream:sum(int(line.split(',',1)[0])==stream for line in lines) for stream in (0,1)}
                    if counts[0]!=spec['frames'] or (profile=='hd60' and counts[1]==0):raise RuntimeError('Strict frame/audio coverage failed')
                    decoded[row['sha256']]={'framehash':str(frames),'sha256':sha256_file(frames),'counts':counts,'lines':lines}
                decoded_value=decoded[row['sha256']]
                result['decodes'][profile+'/'+label]={k:v for k,v in decoded_value.items() if k!='lines'}
                write_json(target,result)
            baseline=next(r for r in report['rows'] if r['profile']==profile and r['label']=='original')['sha256']
            if any(value['lines']!=decoded[baseline]['lines'] for value in decoded.values()):raise RuntimeError('Decoded content changed')
            result['tests'][profile]={'status':'pass','video_frames_per_output':spec['frames'],'audio_frames':decoded[baseline]['counts'][1],
                'decoded_video_audio_identical':True,'distinct_encoded_hashes':len(decoded)}
            write_json(target,result);print(json.dumps({'profile':profile,'status':'pass','frames':spec['frames']}),flush=True)
        result['status']='completed'
    except BaseException as error:result.update(status='failed',error=str(error)[:4000]);raise
    finally:write_json(target,result)
    print(json.dumps({'report':str(target)}))


if __name__=='__main__':main()
