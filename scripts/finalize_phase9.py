#!/usr/bin/python3 -B
"""Cold evidence and queue audit for rejected experimental optimizations."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase9')))
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection
from ffv2.io import sha256_file,write_json
from ffv2.releases import ACTIVE,package_files,verified


def read(path):return json.loads(Path(path).read_text())


def last_json(path):
    content=Path(path).read_text()
    try:return json.loads(content)
    except ValueError:return [json.loads(line) for line in content.splitlines() if line.startswith('{')][-1]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controls',required=True,type=Path)
    parser.add_argument('--raw-analysis',required=True,type=Path)
    parser.add_argument('--default-control',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    if args.output.exists():raise RuntimeError('Preserve existing index')
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    controls=read(args.controls)
    if controls['status']!='completed' or any(s['status']!='completed' for s in controls['steps']):raise RuntimeError('Final controls incomplete')
    results={s['name']:last_json(s['stdout']) for s in controls['steps']}
    quality_path=Path(results['quality']['analysis']);quality=read(quality_path)
    workflow_path=Path(quality['source_report']);workflow=read(workflow_path)
    raw_path=Path(results['raw-confirmation']['report']);raw=read(raw_path)
    unit_path=Path(results['unit']['report']);unit=read(unit_path)
    mcp_path=Path(results['configured-mcp']['directory'])/'report.json';mcp=read(mcp_path)
    analysis=read(args.raw_analysis)
    default_driver=read(args.default_control)
    if default_driver['status']!='completed':raise RuntimeError('Same-tuning default control incomplete')
    default_path=Path(last_json(default_driver['stdout'])['report']);default=read(default_path)
    if default['status']!='completed':raise RuntimeError('Default workflow incomplete')
    if any(r['status']!='completed' for r in (quality,workflow,raw,unit,mcp,analysis)):raise RuntimeError('Evidence incomplete')
    if quality['hd_optimization_promotion_allowed']:raise RuntimeError('Accepted optimization requires a separate release workflow')
    if sha256_file(workflow_path)!=quality['source_sha256']:raise RuntimeError('Workflow changed')
    if not quality['quality_accepted'] or len(unit['runs'])!=2 or any(r['tests']<136 for r in unit['runs']):raise RuntimeError('Quality/regression gate failed')
    if package_files()!=package_files(WORK/'baseline'):raise RuntimeError('Rejected candidate changed production code')
    current=read(ACTIVE);installed=verified(Path(current['manifest']))
    if current['release_id']!='0.6.0-fc5c8de8ba2a58f7' or installed['version']!='0.6.0':raise RuntimeError('Active release changed')
    selected=selection(verify_hashes=True)
    if selected['selection_id']!=current['engine_selection_id']:raise RuntimeError('Engine/code pair changed')
    native=Path(str(lab_path('ffmpeg-v2-core/ffmpeg')))
    if subprocess.check_output(['git','status','--porcelain'],cwd=native,text=True).strip():raise RuntimeError('Original native checkout modified')
    records=[]
    for database in sorted({*WORK.rglob('jobs.sqlite3'),mcp_path.parent/'state/jobs.sqlite3'}):
        if not database.is_file():continue
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as db:
            counts=dict(db.execute('SELECT status,count(*) FROM jobs GROUP BY status'))
        active=sum(counts.get(s,0) for s in ('queued','waiting_resources','running','validating'))
        records.append({'path':str(database),'counts':counts,'active':active})
    if any(r['active'] for r in records):raise RuntimeError('Owned verification jobs still active')
    evidence_paths=[args.controls,args.raw_analysis,args.default_control,default_path,workflow_path,quality_path,raw_path,unit_path,mcp_path,
                    WORK/'diagnostic-analysis.json',WORK/'probe-20261104T043313-38585183/probe.json',
                    WORK/'queue-build-receipts/build.json',ROOT/'docs/experiments/phase9-frame-queue-capacity.patch',
                    ROOT/'docs/experiments/phase9-hd-lookahead.patch']
    studies=[WORK/name/'report.json' for name in ('reproduce-20261104T031956-d74be804',
        'filters-20261104T033720-77fe960c','probe-20261104T034953-20d85f36',
        'queue-20261104T041439-6f037717','lookahead-20261104T042208-f25f86bd')]+[workflow_path,raw_path,default_path]
    encoding_runs=0;encoded_frames=0
    for path in studies:
        report=read(path)
        if report['status']!='completed':raise RuntimeError('Incomplete study')
        for row in report['rows']:
            if sha256_file(Path(row['output']))!=row['sha256']:raise RuntimeError('Retained media changed')
            encoding_runs+=1;encoded_frames+=900 if row['profile']=='raw30' else 1800
    for name in ('probe-20261104T033408-0e70d77e','probe-20261104T043313-38585183'):
        path=WORK/name/'probe.json';report=read(path);evidence_paths.append(path)
        if report['status']!='completed':raise RuntimeError('Observer incomplete')
        for row in report['cases']:
            if sha256_file(Path(row['output']))!=row['output_sha256']:raise RuntimeError('Probed media changed')
            encoding_runs+=1;encoded_frames+=900 if row['profile']=='raw30' else 1800
    evidence_paths+=studies
    raw_comparison=analysis['reports'][0]['comparisons']['raw30/baseline']
    raw_closed=raw_comparison['native_stock_ratio']<=1 and raw_comparison['block_bootstrap_95_percent'][1]<=1.02
    result={'status':'completed','phase':9,'maintainer':'Jillur Rahman','date':'2026-11-04',
            'investigation_completed':True,'phase9_performance_goal_complete':False,'performance_fix_accepted':False,
            'release_action':'পরীক্ষামূলক পরিবর্তন গৃহীত হয়নি; verified 0.6.0 বহাল।',
            'active_release':current,'engine_selection_id':selected['selection_id'],
            'production_package_sha256':package_files(),'evidence':{str(p):sha256_file(p) for p in evidence_paths},
            'hd_candidate_vs_frozen_native':workflow['vs_frozen_native'],'hd_candidate_vs_matched_stock':workflow['comparison'],
            'unchanged_default_hd_vs_matched_stock':default['comparison'],
            'quality':{k:quality[k] for k in ('frames','quality_deltas','size_ratio','quality_gates','quality_accepted')},
            'independent_raw_vs_matched_stock':raw_comparison,'raw_stock_gap_closed':raw_closed,
            'unit_runtime_tests':unit['runs'],'configured_mcp_checks':mcp['checks'],
            'owned_queue_audit':records,'owned_active_jobs':sum(r['active'] for r in records),
            'coverage':{'actual_encoding_runs':encoding_runs,'encoded_frames':encoded_frames,
                        'candidate_full_workflow_jobs':len(workflow['rows']),'default_full_workflow_jobs':len(default['rows'])},
            'scope':'একই M4 Max ও retained source; epochs আলাদা, warmups excluded, সব slow trial retained। Codec quality বা স্থায়ী Stock gap fix সম্পর্কে অনুমোদনহীন দাবি নেই।'}
    write_json(args.output,result)
    print(json.dumps({'index':str(args.output),'databases':len(records),'active_jobs':result['owned_active_jobs'],
                      'performance_fix_accepted':False,'raw_stock_gap_closed':raw_closed}))


if __name__=='__main__':main()
