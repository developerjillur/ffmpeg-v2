#!/usr/bin/python3 -B
"""All-frame quality against the frozen HD/raw references, with exact-SHA reuse."""
from __future__ import annotations
from public_paths import lab_path, project_path
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


def read(path):return json.loads(Path(path).read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path)
    parser.add_argument('--reuse-quality',type=Path,action='append',default=[]);args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    report=read(args.report)
    if report['status']!='completed':raise RuntimeError('Completed immutable encodes required')
    target=args.report.with_name('quality.json')
    if target.exists():raise RuntimeError('Preserve existing quality evidence')
    reusable=[]
    for path in args.reuse_quality:
        prior=read(path);prior_report=read(prior['source_report'])
        if prior['status']!='completed' or prior_report['status']!='completed' or sha256_file(Path(prior['source_report']))!=prior['source_sha256']:
            raise RuntimeError('Reused quality source identity failed')
        if prior_report['specifications']!=report['specifications']:
            raise RuntimeError('Reused quality requires identical source/range/fps/encoding specifications')
        reusable.extend(dict(q,origin='exact output/source SHA reuse: '+str(path)) for q in prior['quality'].values())
    old_path=Path(str(lab_path('ffmpeg-v2-phase8/confirm-20261103T181013-bc270fb1/quality.json')))
    old=read(old_path);old_analysis=read(old_path.with_name('analysis.json'))
    if old['status']!='completed' or sha256_file(old_path)!=old_analysis['quality_sha256']:raise RuntimeError('Old quality changed')
    hd=read(Path(old['source_report']))['profiles']['bbb-1080']
    raw_path=Path(str(lab_path('ffmpeg-v2-phase8/isolation-20261103T182305-6a8a3972/isolation.json')))
    raw=read(raw_path)['raw']
    sources={'hd60':{'path':hd['input'],'sha256':hd['source_sha256'],'frames':1800,'argv':['-ss','60','-i',hd['input']]},
             'raw30':{'path':raw['path'],'sha256':raw['sha256'],'frames':900,'argv':['-f','rawvideo','-pixel_format','yuv420p','-video_size','1920x1080','-framerate','30','-i',raw['path']]}}
    for spec in sources.values():
        if sha256_file(Path(spec['path']))!=spec['sha256']:raise RuntimeError('Reference source changed')
    result={'status':'running','source_report':str(args.report),'source_sha256':sha256_file(args.report),
            'quality':{},'comparisons':{},'thresholds':{'vmaf_delta_min':-.10,'psnr_y_delta_min':-.05,'ssim_delta_min':-.00001,'size_ratio_max':1.02}}
    directory=args.report.parent/'quality';directory.mkdir(mode=0o700)
    selected=selection(verify_hashes=True);verify=Verification(Path(selected['install_prefix']),directory/'guarded')
    for profile,spec in sources.items():
        if profile not in report['specifications']:continue
        for label in report['configurations']:
            rows=[r for r in report['rows'] if r['profile']==profile and r['label']==label]
            if not rows or len({r['sha256'] for r in rows})!=1:raise RuntimeError('Deterministic output required')
            row=rows[0]
            for current in rows:
                if sha256_file(Path(current['output']))!=current['sha256']:raise RuntimeError('Output changed')
            match=next((q for q in result['quality'].values() if q['output_sha256']==row['sha256'] and q['source_sha256']==spec['sha256']),None)
            if not match:
                match=next((q for q in reusable if q['output_sha256']==row['sha256'] and q['source_sha256']==spec['sha256'] and q['frames']==spec['frames']),None)
            if not match and profile=='hd60':
                candidate=old['quality']['bbb-1080/candidate-native']
                if candidate['output_sha256']==row['sha256'] and candidate['source_sha256']==spec['sha256']:
                    match={**candidate,'origin':'exact frozen 0.6.0 encoded SHA and identical source/range/fps'}
            if not match:
                metric=directory/(profile+'-'+label+'.json');frames=spec['frames']
                graph=(f'[0:v]trim=end_frame={frames},settb=AVTB,setpts=N/(30*TB)[test];'
                       f'[1:v]trim=end_frame={frames},scale=1920:1080:flags=lanczos,settb=AVTB,setpts=N/(30*TB)[ref];'
                       '[test][ref]libvmaf=log_fmt=json:log_path='+str(metric)+':n_threads=2:feature=name=psnr|name=float_ssim:shortest=1')
                receipt=verify.aux(profile+'-'+label,[selected['binaries']['ffmpeg'],'-v','error','-nostdin','-filter_complex_threads','1',
                    '-threads','2','-i',row['output'],'-threads','2',*spec['argv'],'-filter_complex',graph,'-an','-threads','2','-f','null','-'],metric,timeout=1200,budget=64*1024**2)
                data=read(metric)
                match={'report':str(metric),'metric_sha256':sha256_file(metric),'frames':len(data['frames']),
                       'metrics':data['pooled_metrics'],'origin':'new_all_frame_measurement'}
            data=read(match['report'])
            if sha256_file(Path(match['report']))!=match['metric_sha256'] or len(data['frames'])!=spec['frames'] or data['pooled_metrics']!=match['metrics']:
                raise RuntimeError('Metric identity/frame coverage failed')
            result['quality'][profile+'/'+label]={**match,'output_sha256':row['sha256'],'source_sha256':spec['sha256']}
            write_json(target,result);print(json.dumps({'quality':profile+'/'+label,'frames':spec['frames'],'vmaf':match['metrics']['vmaf']['mean'],'origin':match['origin']}),flush=True)
        baseline=result['quality'][profile+'/original']
        for label in report['configurations']:
            q=result['quality'][profile+'/'+label]
            deltas={name:q['metrics'][key]['mean']-baseline['metrics'][key]['mean'] for name,key in (('vmaf','vmaf'),('psnr_y','psnr_y'),('ssim','float_ssim'))}
            a=next(r for r in report['rows'] if r['profile']==profile and r['label']=='original')
            b=next(r for r in report['rows'] if r['profile']==profile and r['label']==label)
            size=b['bytes']/a['bytes'];gates={'vmaf':deltas['vmaf']>=-.10,'psnr_y':deltas['psnr_y']>=-.05,'ssim':deltas['ssim']>=-.00001,'size':size<=1.02}
            result['comparisons'][profile+'/'+label]={'deltas':deltas,'size_ratio':size,'gates':gates,'quality_accepted':all(gates.values())}
    result['status']='completed';write_json(target,result)
    print(json.dumps({'quality_report':str(target),'comparisons':result['comparisons']}))


if __name__=='__main__':main()
