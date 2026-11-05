#!/usr/bin/python3 -B
"""Immutable timing receipts, exact-file all-frame quality and paired gates."""
from __future__ import annotations
from public_paths import lab_path, project_path

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.engine import selection
from ffv2.io import sha256_file, write_json

PREVIOUS = Path(str(lab_path('ffmpeg-v2-phase4/acceptance-20261103T170546-0cf42211/report.json')))


def read(path):
    return json.loads(path.read_text())


def quality(report, timing_path, reuse_paths):
    from verify_phase2 import Verification
    target = timing_path.with_name('quality.json')
    checksum = sha256_file(timing_path)
    result = read(target) if target.exists() else {
        'status': 'running', 'source_report': str(timing_path), 'source_sha256': checksum,
        'quality': {}, 'quality_thresholds': report['quality_thresholds']}
    if result['source_sha256'] != checksum:
        raise RuntimeError('Timing report changed after quality began')
    old_reports = []
    for path in [PREVIOUS] + reuse_paths:
        old = read(path)
        if old['status'] != 'completed':
            raise RuntimeError('Only completed quality may be reused')
        timing = read(Path(old['source_report'])) if 'source_report' in old else old
        if 'source_report' in old and sha256_file(Path(old['source_report'])) != old['source_sha256']:
            raise RuntimeError('Reused timing evidence changed')
        old_reports.append((path, timing, old['quality']))
    selected = selection(verify_hashes=True)
    if selected['selection_id'] != report['engine_selection_id']:
        raise RuntimeError('Native selection differs from timing')
    verify = None
    for profile, source in report['profiles'].items():
        if sha256_file(Path(source['input'])) != source['source_sha256']:
            raise RuntimeError('Reference source changed')
        for label in report['configurations']:
            key = profile+'/'+label
            rows = [r for r in report['cases'] if r['profile']==profile and r['label']==label]
            hashes = {r['sha256'] for r in rows}
            if len(hashes) != 1 or len(rows) != report['trials']+1:
                raise RuntimeError('Each complete configuration must produce one deterministic output')
            row = rows[0]
            for current in rows:
                if sha256_file(Path(current['output'])) != current['sha256']:
                    raise RuntimeError('Saved media changed')
                receipt = read(Path(current['receipt']))
                metadata = receipt['validation']['metadata']
                if (receipt['status'] != 'completed' or receipt['output_sha256'] != current['sha256'] or
                        int(metadata['video']['nb_frames']) != report['seconds']*source['fps'] or
                        metadata['video']['width'] != source['width'] or metadata['video']['height'] != source['height'] or
                        not metadata.get('audio') or abs(metadata['duration_seconds']-report['seconds']) > .1):
                    raise RuntimeError('Published output failed full workflow metadata/integrity gates')
            if key in result['quality']:
                saved = result['quality'][key]
                if saved['output_sha256'] != row['sha256'] or sha256_file(Path(saved['report'])) != saved['metric_sha256']:
                    raise RuntimeError('Saved quality changed')
                continue
            match = next((q for q in result['quality'].values()
                          if q['output_sha256']==row['sha256'] and q['source_sha256']==source['source_sha256']), None)
            origin = str(target)
            if match is None:
                for old_path, old, qualities in old_reports:
                    if old['seconds'] != report['seconds'] or old['start_seconds'] != report['start_seconds']:
                        continue
                    found = next((r for r in old['cases'] if r['sha256']==row['sha256'] and
                                  old['profiles'][r['profile']]['source_sha256']==source['source_sha256'] and
                                  old['profiles'][r['profile']]['fps']==source['fps'] and
                                  r['profile']+'/'+r['label'] in qualities), None)
                    if found:
                        match, origin = qualities[found['profile']+'/'+found['label']], str(old_path)
                        break
            expected = report['seconds']*source['fps']
            if match is None:
                if verify is None:
                    verify = Verification(Path(selected['install_prefix']), timing_path.parent/'quality')
                metric = timing_path.parent/'quality'/(profile+'-'+label+'.json')
                if not metric.exists():
                    fps = source['fps']
                    graph = (f'[0:v]trim=end_frame={expected},settb=AVTB,setpts=N/({fps}*TB)[test];'
                             f"[1:v]trim=end_frame={expected},scale={source['width']}:{source['height']}:flags=lanczos,settb=AVTB,setpts=N/({fps}*TB)[ref];"
                             '[test][ref]libvmaf=log_fmt=json:log_path='+str(metric)+':n_threads=2:feature=name=psnr|name=float_ssim:shortest=1')
                    verify.aux(profile+'-'+label, [selected['binaries']['ffmpeg'],'-v','error','-nostdin',
                        '-filter_complex_threads','1','-threads','2','-i',row['output'],'-threads','2','-ss',
                        str(report['start_seconds']),'-i',source['input'],'-filter_complex',graph,'-an',
                        '-threads','2','-f','null','-'],metric,timeout=1200,budget=64*1024**2)
                data = read(metric)
                match = {'frames':len(data['frames']), 'metrics':data['pooled_metrics'], 'report':str(metric)}
                origin = 'new_all_frame_measurement'
            metric = Path(match['report'])
            data = read(metric)
            if match['frames'] != expected or len(data['frames']) != expected or data['pooled_metrics'] != match['metrics']:
                raise RuntimeError('All-frame quality coverage or metric identity mismatch')
            result['quality'][key] = {**match, 'source_sha256':source['source_sha256'], 'output_sha256':row['sha256'],
                                     'metric_sha256':sha256_file(metric), 'origin':origin}
            write_json(target,result)
            print(json.dumps({'quality':key,'frames':expected,'origin':origin,
                              'vmaf':match['metrics']['vmaf']['mean']}),flush=True)
    result['status'] = 'completed'
    write_json(target,result)
    return target,result


def compare(report, qualities, profile, baseline, candidate):
    a = {r['trial']:r for r in report['cases'] if r['profile']==profile and r['label']==baseline and not r['warmup']}
    b = {r['trial']:r for r in report['cases'] if r['profile']==profile and r['label']==candidate and not r['warmup']}
    if set(a)!=set(b) or len(a)<3:
        raise RuntimeError('At least three independent matched trial blocks required')
    qa,qb = qualities[profile+'/'+baseline],qualities[profile+'/'+candidate]
    deltas = {name:qb['metrics'][metric]['mean']-qa['metrics'][metric]['mean'] for name,metric in
              (('vmaf','vmaf'),('psnr_y','psnr_y'),('ssim','float_ssim'))}
    med_a,med_b = (statistics.median(r['total_seconds'] for r in rows.values()) for rows in (a,b))
    size = statistics.median(r['bytes'] for r in b.values())/statistics.median(r['bytes'] for r in a.values())
    rng,boot = random.Random(202611038),[]
    for _ in range(20000):
        sample = rng.choices(sorted(a),k=len(a))
        boot.append(statistics.median(b[i]['total_seconds'] for i in sample)/statistics.median(a[i]['total_seconds'] for i in sample))
    boot.sort()
    ci = [boot[500],boot[19499]]
    threshold = report['quality_thresholds']
    gates = {'vmaf':deltas['vmaf']>=threshold['vmaf_delta_min'], 'psnr_y':deltas['psnr_y']>=threshold['psnr_y_delta_min'],
             'ssim':deltas['ssim']>=threshold['ssim_delta_min'], 'size':size<=threshold['size_ratio_max'],
             'median_faster':med_b<med_a, 'paired_bootstrap_faster':ci[1]<1}
    return {'baseline':baseline,'candidate':candidate,'n_pairs':len(a),'quality_frames':qb['frames'],
            'quality_deltas':deltas,'size_ratio':size,'baseline_median_seconds':med_a,'candidate_median_seconds':med_b,
            'time_ratio':med_b/med_a,'time_reduction_percent':100*(1-med_b/med_a),
            'paired_bootstrap_ratio_95_percent':ci,'gates':gates,'promotion_allowed':all(gates.values())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report',type=Path)
    parser.add_argument('--reuse-quality',action='append',default=[],type=Path)
    args = parser.parse_args()
    timing = args.report.resolve(strict=True)
    report = read(timing)
    if report['status'] != 'timing_completed':
        raise RuntimeError('Frozen completed timing required')
    target = timing.with_name('analysis.json')
    if target.exists():
        raise RuntimeError('Analysis already exists; retain original evidence')
    quality_path,q = quality(report,timing,args.reuse_quality)
    comparisons = {}
    for profile in report['profiles']:
        if report['mode']=='confirm':
            pairs = [('baseline-native','candidate-native','candidate-native'),
                     ('baseline-stock','candidate-native','vs_previous_stock'),
                     ('candidate-stock','candidate-native','vs_matched_stock')]
        else:
            pairs = [('native4',label,label) for label in report['configurations'] if label!='native4']
        for baseline,candidate,key in pairs:
            comparisons[profile+'/'+key] = compare(report,q['quality'],profile,baseline,candidate)
    accepted = report['mode']=='confirm' and all(comparisons[profile+'/'+key]['promotion_allowed']
        for profile in report['profiles'] for key in ('candidate-native','vs_previous_stock'))
    value = {'status':'completed','phase':8,'mode':report['mode'],'source_report':str(timing),'source_sha256':sha256_file(timing),
             'quality_report':str(quality_path),'quality_sha256':sha256_file(quality_path),'comparisons':comparisons,
             'required_profiles':['bbb-1080','tos-liveaction'],'release_performance_accepted':accepted,
             'statistic':'Ratio of medians; 20000 paired trial-block bootstrap draws, deterministic seed; warmups excluded.'}
    write_json(target,value)
    print(json.dumps({'analysis':str(target),'release_performance_accepted':accepted,
                      'comparisons':comparisons}))


if __name__=='__main__':
    main()
