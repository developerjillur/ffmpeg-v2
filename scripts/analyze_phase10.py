#!/usr/bin/python3 -B
"""Balanced whole-block timing, CPU work and measured synthetic-load evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.io import sha256_file,write_json
from analyze_phase9 import paired_blocks


def compare(rows,reference,draws=20000):
    selected=[dict(row,label='native' if row['label']=='candidate' else 'stock')
              for row in rows if row['label'] in ('candidate',reference)]
    result=paired_blocks(selected,draws=draws)
    result['reference']=reference
    result['improvement_accepted']=result['native_stock_ratio']<1 and result['block_bootstrap_95_percent'][1]<1
    result['stock_gap_closed']=result['native_stock_ratio']<=1 and result['block_bootstrap_95_percent'][1]<=1.02
    return result


def validate_blocks(rows,blocks,labels):
    measured=[r for r in rows if not r['warmup']]
    if {r['block'] for r in measured}!=set(range(blocks)):
        raise ValueError('Predeclared whole blocks are missing')
    if len(measured)!=blocks*len(labels)*2:
        raise ValueError('Unexpected measured observation count')
    for block in range(blocks):
        for label in labels:
            if sum(r['block']==block and r['label']==label for r in measured)!=2:
                raise ValueError('Incomplete balanced control block')


def load_window(child,counters):
    elapsed=child['encoding_wall_seconds'];ticks=child['host_cpu_ticks'];clock=child['host_clock_ticks']
    if elapsed<=0 or clock<=0 or len(ticks)!=4:raise ValueError('Invalid CPU window')
    capacity=sum(ticks)/clock/elapsed
    busy=(ticks[0]+ticks[1]+ticks[3])/clock/elapsed
    synthetic=0
    for worker in child['load_workers']:
        if not worker['rusage_v6'] or worker['duty']!=50 or worker['iterations']<=0 or worker['mach_denom']<=0:
            raise ValueError('Owned load proof failed')
        synthetic+=worker['window_cpu_mach']*worker['mach_numer']/worker['mach_denom']/1e9/elapsed
    encode=(counters['user_seconds']+counters['sys_seconds'])/elapsed
    return {'host_capacity_cores':capacity,'host_busy_cores':busy,'synthetic_cpu_cores':synthetic,
            'encoding_cpu_cores':encode,'residual_busy_cores_estimate':busy-synthetic-encode,
            'note':'Residual is an estimate from separate rounded accounting windows; unrelated activity is observed, not controlled.'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('report',type=Path)
    parser.add_argument('--quality',type=Path);args=parser.parse_args()
    report=json.loads(args.report.read_text());target=args.report.with_name('analysis.json')
    if target.exists():raise RuntimeError('Preserve completed analysis')
    if report['status']!='completed' or report['mode']!='confirm' or report['blocks']<3:
        raise RuntimeError('Independent complete confirmation required')
    quality_path=args.quality or args.report.with_name('quality.json');quality=json.loads(quality_path.read_text())
    if quality['status']!='completed' or quality['source_sha256']!=sha256_file(args.report):
        raise RuntimeError('Quality must bind the same timing report')
    result={'status':'running','phase':10,'mode':'confirm','source_report':str(args.report),
            'source_sha256':sha256_file(args.report),'quality_report':str(quality_path),
            'quality_sha256':sha256_file(quality_path),'comparisons':{},'cpu_work':{},'cpu_work_comparisons':{},'load_windows':{},
            'statistic':'Ratio of medians; 20000 whole palindrome-block bootstrap resamples; warmups excluded; load epochs separate.',
            'release_performance_accepted':False}
    for profile in report['specifications']:
        if not quality['comparisons'][profile+'/candidate']['quality_accepted']:raise RuntimeError('Candidate quality failed')
        for load in report['load_levels']:
            rows=[r for r in report['rows'] if r['profile']==profile and r['load']==load]
            validate_blocks(rows,report['blocks'],report['configurations'])
            for row in rows:
                if sha256_file(Path(row['output']))!=row['sha256']:raise RuntimeError('Encoded media changed')
            key=profile+'/load'+str(load)
            result['comparisons'][key]={reference:compare(rows,reference) for reference in ('original','stock')}
            result['cpu_work_comparisons'][key]={}
            for metric in ('instructions','cpu_seconds'):
                mapped=[dict(r,seconds=r['counters']['instructions_retired'] if metric=='instructions' else r['counters']['user_seconds']+r['counters']['sys_seconds']) for r in rows]
                result['cpu_work_comparisons'][key][metric]={reference:compare(mapped,reference) for reference in ('original','stock')}
            result['cpu_work'][key]={}
            result['load_windows'][key]={}
            for label in report['configurations']:
                measured=[r for r in rows if not r['warmup'] and r['label']==label]
                result['cpu_work'][key][label]={
                    'cpu_seconds':statistics.median(r['counters']['user_seconds']+r['counters']['sys_seconds'] for r in measured),
                    'instructions':statistics.median(r['counters']['instructions_retired'] for r in measured),
                    'peak_job_bytes_max':max(r['peak_job_memory_bytes'] for r in measured)}
                windows=[]
                for row in measured:
                    path=Path(row['child_report']);child=json.loads(path.read_text())
                    if child['status']!='completed' or child['exit_code'] or len(child['load_workers'])!=load:
                        raise RuntimeError('Controlled-load child incomplete')
                    windows.append(dict(load_window(child,row['counters']),path=str(path),sha256=sha256_file(path)))
                result['load_windows'][key][label]={'samples':windows,
                    'medians':{k:statistics.median(w[k] for w in windows) for k in windows[0] if k not in ('path','sha256','note')}}
    result['release_performance_accepted']=all(v['original']['improvement_accepted'] and v['stock']['stock_gap_closed']
        for v in result['comparisons'].values())
    result['status']='completed';write_json(target,result)
    print(json.dumps({'analysis':str(target),'accepted':result['release_performance_accepted'],'comparisons':result['comparisons']}))


if __name__=='__main__':main()
