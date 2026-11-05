#!/usr/bin/python3 -B
"""Whole-block paired speed ratios for predeclared stable environments."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import random
import statistics

from phase11_common import read
from conditions_phase11 import DEFAULT_POLICY,validate_block,validate_case
from ffv2.io import sha256_file,write_json


def paired(rows,reference,draws=20000):
    blocks=sorted({r['block'] for r in rows});logs=[];details=[]
    if len(blocks)<3:raise ValueError('Independent whole blocks required')
    for block in blocks:
        values={label:[r['seconds'] for r in rows if r['block']==block and r['label']==label] for label in ('candidate',reference)}
        if any(len(v)!=2 for v in values.values()):raise ValueError('Incomplete paired control block')
        if any(not math.isfinite(t) or t<=0 for value in values.values() for t in value):raise ValueError('Finite positive process durations required')
        ratio=statistics.mean(values['candidate'])/statistics.mean(values[reference]);logs.append(math.log(ratio))
        details.append({'block':block,'ratio':ratio,'seconds':values})
    rng=random.Random(2026110411);boot=sorted(math.exp(statistics.mean(rng.choices(logs,k=len(logs)))) for _ in range(draws))
    interval=[boot[int(draws*.025)],boot[int(draws*.975)-1]];ratio=math.exp(statistics.mean(logs))
    return {'blocks':len(blocks),'n_per_engine':2*len(blocks),'paired_geometric_mean_ratio':ratio,
        'time_change_percent':100*(ratio-1),'whole_block_95_percent':interval,'speedup_proven':ratio<1 and interval[1]<1,
        'candidate_median_seconds':statistics.median(r['seconds'] for r in rows if r['label']=='candidate'),
        'reference_median_seconds':statistics.median(r['seconds'] for r in rows if r['label']==reference),'block_ratios':details}


def cache_proof(report,rows,profile):
    identities={r['cache_hold_id'] for r in rows}
    if len(identities)!=1:raise RuntimeError('A paired block must share one unbroken cache generation')
    held=report['cache_holds'][next(iter(identities))];inputs=[str(Path(report['sources'][profile]['path']).resolve(strict=True))]
    images=sorted(set().union(*(set(c) for c in report['engine_files'].values()))-set(inputs))
    if held['status']!='completed' or not held['unbroken'] or held['sources']!=inputs or held['images']!=images:
        raise RuntimeError('Unbroken common cache hold required')
    if held['source_bytes']>3*1024**3 or held['image_bytes']>256*1024**2 or held['peak_accounted_bytes']>12*1024**3:
        raise RuntimeError('Cache size/resource bound exceeded')
    if {p['path'] for p in held['proof']}!=set(inputs+images):raise RuntimeError('Cache hold proof incomplete')
    if any(not p['unchanged'] or p['resident_before']!=p['pages'] or p['resident_after']!=p['pages'] for p in held['proof']):
        raise RuntimeError('Cache hold residency changed')
    return held


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path);args=parser.parse_args()
    report=read(args.report);target=args.report.with_name('analysis.json')
    if target.exists():raise RuntimeError('Preserve analysis')
    if report['status']!='completed' or report['mode']!='confirm' or report['required_valid_blocks']<9:
        raise RuntimeError('Complete predeclared nine-block confirmation required')
    if report['environment_policy']!=DEFAULT_POLICY:raise RuntimeError('Predeclared conditioning policy changed')
    result={'status':'running','phase':11,'source_report':str(args.report),'source_sha256':sha256_file(args.report),
        'comparisons':{},'accepted_blocks':{},'rejected_blocks':{},'release_performance_accepted':False,
        'estimator':'Geometric mean of within-block mean-time ratios; 20000 whole-block bootstrap draws. No pooling of load states.'}
    pipeline=report.get('pipeline',False)
    quality=read(Path(report['quality']['path']))
    if sha256_file(Path(report['quality']['path']))!=report['quality']['sha256'] or quality['status']!='completed':
        raise RuntimeError('Quality evidence changed')
    if sha256_file(Path(report['quality']['decoded_identity']))!=report['quality']['decoded_identity_sha256']:
        raise RuntimeError('Decoded identity evidence changed')
    if not all(v['quality_accepted'] for v in quality['comparisons'].values()):raise RuntimeError('Quality gate failed')
    qreport=read(Path(quality['source_report']))
    if qreport['status']!='completed' or sha256_file(Path(quality['source_report']))!=quality['source_sha256']:raise RuntimeError('Quality source changed')
    identity=read(Path(report['quality']['decoded_identity']))
    if identity['status']!='completed' or identity['source_sha256']!=quality['source_sha256']:raise RuntimeError('Decoded identity source mismatch')
    for profile,spec in report['specifications'].items():
        if spec!=qreport['specifications'][profile]:raise RuntimeError('Quality workload differs')
        for label in report['configurations']:
            expected=next(r['sha256'] for r in qreport['rows'] if r['profile']==profile and r['label']==label)
            if report['quality']['expected_output_sha256'][profile][label]!=expected:raise RuntimeError('Quality output binding differs')
    for label,configuration in report['configurations'].items():
        binary=configuration['ffmpeg'] if pipeline else configuration
        if binary!=qreport['configurations'][label]:raise RuntimeError('Quality encoder differs')
        if any(report['engine_files'][label].get(p)!=value for p,value in qreport['engine_files'][label].items()):
            raise RuntimeError('Quality runtime differs')
    log=Path(report['directory'])/'admission.jsonl'
    if sha256_file(log)!=report['admission_log_sha256']:raise RuntimeError('Automatic window log changed')
    by_counter={r['counter']:r for r in report['rows']}
    result['insufficient_groups']=[]
    required_profiles={'hd60'} if pipeline else {'hd60','raw30'}
    for profile in required_profiles:
        for load in (0,2):
            if profile not in report['specifications'] or load not in report['load_levels']:result['insufficient_groups'].append(profile+'/load'+str(load))
    for profile in report['specifications']:
        for load in report['load_levels']:
            key=profile+'/load'+str(load);blocks=[b for b in report['blocks'] if b['profile']==profile and b['load']==load]
            accepted=[b for b in blocks if b['validation']['valid']]
            sufficient=len(accepted)==report['required_valid_blocks'] and {b['block'] for b in accepted}==set(range(report['required_valid_blocks']))
            if not sufficient:result['insufficient_groups'].append(key)
            rows=[]
            for block in accepted:
                values=[by_counter[name] for name in block['rows']]
                held=cache_proof(report,values,profile)
                checked=[]
                for row in values:
                    if row['cache_hold_id']!=held['lease_id']:raise RuntimeError('Case cache generation differs')
                    counter=Path(row['counter']);data=read(counter)
                    if sha256_file(counter)!=row['counter_sha256'] or sha256_file(Path(row['output']))!=row['sha256']:
                        raise RuntimeError('Measured artifact changed')
                    if row['sha256']!=report['quality']['expected_output_sha256'][profile][row['label']]:raise RuntimeError('Quality output mismatch')
                    environment=validate_case(data,load,report['environment_policy'],pipeline=pipeline)
                    if not environment['valid']:raise RuntimeError('Invalid environment in accepted block')
                    checked.append(dict(row,environment=environment))
                validation=validate_block(checked,list(report['configurations']),load,report['environment_policy'],pipeline=pipeline)
                if not validation['valid']:raise RuntimeError('Whole-block stability failed')
                rows.extend(values)
            if rows:
                for label in report['configurations']:
                    if len({r['sha256'] for r in rows if r['label']==label})!=1:raise RuntimeError('Non-deterministic output')
            result['comparisons'][key]={label:paired(rows,label) for label in ('original','stock')} if len(accepted)>=3 else {}
            result['accepted_blocks'][key]=len(accepted);result['rejected_blocks'][key]=len(blocks)-len(accepted)
    result['release_performance_accepted']=not result['insufficient_groups'] and all(row['speedup_proven'] for group in result['comparisons'].values() for row in group.values())
    result['status']='completed';write_json(target,result)
    print(json.dumps({'analysis':str(target),'accepted':result['release_performance_accepted'],'comparisons':result['comparisons']}))


if __name__=='__main__':main()
