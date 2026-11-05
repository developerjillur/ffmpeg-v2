#!/usr/bin/python3 -B
"""All-frame quality and independent speed gates for the scoped HD candidate."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification


def read(path):return json.loads(Path(path).read_text())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path);args=parser.parse_args()
    report=read(args.report)
    if report['status']!='completed' or 'vs_frozen_native' not in report:raise RuntimeError('Completed independent candidate control required')
    target=args.report.with_name('analysis.json')
    if target.exists():raise RuntimeError('Preserve existing analysis')
    old_path=Path(str(lab_path('ffmpeg-v2-phase8/confirm-20261103T181013-bc270fb1/quality.json')))
    old=read(old_path);baseline=old['quality']['bbb-1080/candidate-native']
    accepted=read(old_path.with_name('analysis.json'));old_timing=read(old['source_report'])
    if (accepted['status']!='completed' or sha256_file(old_path)!=accepted['quality_sha256'] or
            sha256_file(Path(old['source_report']))!=old['source_sha256'] or
            old_timing['seconds']!=60 or old_timing['start_seconds']!=60 or
            old_timing['profiles']['bbb-1080']['fps']!=30):
        raise RuntimeError('Baseline timing/quality provenance mismatch')
    metric=read(baseline['report']);source=report['source']
    if (old['status']!='completed' or sha256_file(Path(baseline['report']))!=baseline['metric_sha256'] or
            len(metric['frames'])!=1800 or metric['pooled_metrics']!=baseline['metrics'] or
            sha256_file(Path(source['input']))!=baseline['source_sha256'] or source['source_sha256']!=baseline['source_sha256']):
        raise RuntimeError('Baseline all-frame quality changed')
    rows={label:[r for r in report['rows'] if r['label']==label] for label in report['configurations']}
    for label,group in rows.items():
        if len(group)!=2*report['blocks']+1 or len({r['sha256'] for r in group})!=1:raise RuntimeError('Incomplete deterministic workflow')
        for row in group:
            receipt=read(row['receipt'])
            if (sha256_file(Path(row['output']))!=row['sha256'] or receipt['output_sha256']!=row['sha256'] or
                    int(receipt['validation']['metadata']['video']['nb_frames'])!=1800 or
                    not receipt['validation']['metadata'].get('audio')):raise RuntimeError('Published media changed')
    if rows['baseline-native'][0]['sha256']!=baseline['output_sha256']:raise RuntimeError('Baseline output differs')
    candidate=rows['native'][0]
    if candidate['sha256']!=rows['stock'][0]['sha256']:raise RuntimeError('Same-tuning Native/Stock differ')
    selected=selection(verify_hashes=True)
    verify=Verification(Path(selected['install_prefix']),args.report.parent/'quality')
    metric_path=args.report.parent/'quality/candidate-all-frames.json'
    graph=('[0:v]trim=end_frame=1800,settb=AVTB,setpts=N/(30*TB)[test];'
           '[1:v]trim=end_frame=1800,scale=1920:1080:flags=lanczos,settb=AVTB,setpts=N/(30*TB)[ref];'
           '[test][ref]libvmaf=log_fmt=json:log_path='+str(metric_path)+':n_threads=2:feature=name=psnr|name=float_ssim:shortest=1')
    verify.aux('all-frame-quality',[selected['binaries']['ffmpeg'],'-v','error','-nostdin','-filter_complex_threads','1',
        '-threads','2','-i',candidate['output'],'-threads','2','-ss','60','-i',source['input'],
        '-filter_complex',graph,'-an','-threads','2','-f','null','-'],metric_path,timeout=1200,budget=64*1024**2)
    measured=read(metric_path)
    if len(measured['frames'])!=1800:raise RuntimeError('Full quality coverage required')
    metrics=measured['pooled_metrics']
    deltas={name:metrics[key]['mean']-baseline['metrics'][key]['mean'] for name,key in
            (('vmaf','vmaf'),('psnr_y','psnr_y'),('ssim','float_ssim'))}
    size=candidate['bytes']/rows['baseline-native'][0]['bytes']
    quality_gates={'vmaf':deltas['vmaf']>=-.10,'psnr_y':deltas['psnr_y']>=-.05,
                   'ssim':deltas['ssim']>=-.00001,'size':size<=1.02}
    speed=report['vs_frozen_native'];stock=report['comparison']
    speed_gate=speed['native_stock_ratio']<1 and speed['block_bootstrap_95_percent'][1]<1
    closed=stock['native_stock_ratio']<=1 and stock['block_bootstrap_95_percent'][1]<=1.02
    value={'status':'completed','phase':9,'scope':'HD-only lookahead candidate; raw inputs excluded from this policy.',
           'source_report':str(args.report),'source_sha256':sha256_file(args.report),
           'baseline_quality':str(old_path),'baseline_quality_sha256':sha256_file(old_path),
           'metric_report':str(metric_path),'metric_sha256':sha256_file(metric_path),'frames':1800,
           'output_sha256':candidate['sha256'],'source_media_sha256':source['source_sha256'],
           'metrics':metrics,'quality_deltas':deltas,'size_ratio':size,'quality_gates':quality_gates,
           'quality_accepted':all(quality_gates.values()),'vs_frozen_native':speed,'vs_matched_stock':stock,
           'independent_native_speed_accepted':speed_gate,'hd_stock_gap_closed':closed,
           'hd_optimization_promotion_allowed':speed_gate and all(quality_gates.values())}
    write_json(target,value);print(json.dumps({'analysis':str(target),'quality_deltas':deltas,'size_ratio':size,
        'speed_accepted':speed_gate,'hd_stock_gap_closed':closed,'promotion_allowed':value['hd_optimization_promotion_allowed']}))


if __name__=='__main__':main()
