#!/usr/bin/python3 -B
"""Analyse retained balanced runs without treating observations as independent pairs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import random
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.io import sha256_file,write_json


def paired_blocks(rows, *, draws=20000):
    measured=[r for r in rows if not r['warmup']]
    blocks=sorted({r['block'] for r in measured})
    if len(blocks)<2:raise ValueError('At least two complete blocks required')
    grouped={};observations={}
    for block in blocks:
        group={label:[r['seconds'] for r in measured if r['block']==block and r['label']==label]
               for label in ('native','stock')}
        if any(len(v)!=2 for v in group.values()):raise ValueError('Incomplete ABBA/BAAB block')
        observations[block]=group
        grouped[block]={k:statistics.median(v) for k,v in group.items()}
    native=statistics.median(r['seconds'] for r in measured if r['label']=='native')
    stock=statistics.median(r['seconds'] for r in measured if r['label']=='stock')
    rng=random.Random(202611049)
    boot=[]
    for _ in range(draws):
        sample=rng.choices(blocks,k=len(blocks))
        boot.append(statistics.median(v for b in sample for v in observations[b]['native'])/
                    statistics.median(v for b in sample for v in observations[b]['stock']))
    boot.sort()
    interval=[boot[int(draws*.025)],boot[int(draws*.975)-1]]
    return {'blocks':len(blocks),'n_per_engine':len(measured)//2,'native_median_seconds':native,
            'stock_median_seconds':stock,'native_stock_ratio':native/stock,
            'slowdown_percent':100*(native/stock-1),'block_bootstrap_95_percent':interval,
            'native_faster_supported':interval[1]<1,'stock_faster_supported':interval[0]>1,
            'block_medians':grouped,'statistical_unit':'whole adjacent block; experiment role is set by the caller'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('reports',nargs='+',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise RuntimeError('Preserve existing analysis')
    result={'status':'running','phase':9,'reports':[],
            'statistic':'Ratio of overall medians; 20000 resamples of whole adjacent ABBA/BAAB blocks. Warmups excluded. Epochs and variants never pooled.',
            'release_performance_accepted':False}
    for path in args.reports:
        report=json.loads(path.read_text())
        if report['status']!='completed':raise RuntimeError('Completed timing required')
        if not all(r['reference_bit_identical'] for r in report['rows']):
            raise RuntimeError('Changed output requires fresh all-frame quality')
        groups={}
        for profile in report['specifications']:
            for variant in report['variants']:
                rows=[r for r in report['rows'] if r['profile']==profile and r['variant']==variant]
                if len({r['sha256'] for r in rows})!=1:raise RuntimeError('Non-deterministic output')
                for row in rows:
                    if sha256_file(Path(row['output']))!=row['sha256']:raise RuntimeError('Media changed')
                groups[profile+'/'+variant]=paired_blocks(rows)
        result['reports'].append({'path':str(path.resolve()),'sha256':sha256_file(path),
                                  'mode':report['mode'],'comparisons':groups})
    result['status']='completed';write_json(args.output,result)
    print(json.dumps({'output':str(args.output),'epochs':len(result['reports'])}))


if __name__=='__main__':main()
