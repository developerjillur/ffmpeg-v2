#!/usr/bin/python3 -B
"""Re-audit actual conditioned counters before creating release performance evidence."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path

from phase11_common import ROOT,read
from analyze_phase11 import paired,cache_proof
from conditions_phase11 import DEFAULT_POLICY,validate_case,validate_block
from ffv2.engine import library_closure
from ffv2.io import sha256_file,write_json
from ffv2.releases import package_files


def speed_groups(value,*,pipeline):
    expected={p+'/load'+str(load) for p in (('hd60',) if pipeline else ('hd60','raw30')) for load in (0,2)}
    if (value.get('status')!='completed' or value.get('phase')!=11 or not value.get('release_performance_accepted') or
            value.get('insufficient_groups') or set(value.get('comparisons',{}))!=expected):
        raise RuntimeError('All predeclared Phase 11 speed groups must pass')
    for key,group in value['comparisons'].items():
        if set(group)!={'original','stock'} or value['accepted_blocks'][key]!=9:raise RuntimeError('Nine paired blocks and both controls required')
        for row in group.values():
            interval=row['whole_block_95_percent'];ratio=row['paired_geometric_mean_ratio']
            if (row['blocks']!=9 or row['n_per_engine']!=18 or not row['speedup_proven'] or len(interval)!=2 or
                    not all(math.isfinite(x) for x in [ratio,*interval]) or not 0<interval[0]<=ratio<=interval[1]<1):
                raise RuntimeError('Reliable same-quality elapsed improvement required')


def record(path):return {'path':str(Path(path).resolve(strict=True)),'sha256':sha256_file(Path(path))}


def linked(value):
    path=Path(value['path'])
    if sha256_file(path)!=value['sha256']:raise RuntimeError('Linked evidence changed')
    return read(path)


def runtime_binding(timing,quality,*,pipeline):
    for label,configuration in timing['configurations'].items():
        binary=configuration['ffmpeg'] if pipeline else configuration
        paths=[Path(configuration[name]) for name in ('ffmpeg','ffprobe')] if pipeline else [Path(binary)]
        if library_closure(paths)!=timing['engine_files'][label]:
            raise RuntimeError('Measured runtime closure changed')
        if binary!=quality['configurations'][label] or any(timing['engine_files'][label].get(p)!=v for p,v in quality['engine_files'][label].items()):
            raise RuntimeError('Quality tested different encoder libraries')


def audit(path,*,pipeline):
    analysis=read(path);speed_groups(analysis,pipeline=pipeline)
    raw=Path(analysis['source_report']);timing=read(raw)
    if sha256_file(raw)!=analysis['source_sha256'] or timing['status']!='completed' or timing.get('pipeline',False)!=pipeline:
        raise RuntimeError('Immutable complete timing required')
    profiles={'hd60'} if pipeline else {'hd60','raw30'}
    if (timing['mode']!='confirm' or timing['required_valid_blocks']!=9 or set(timing['specifications'])!=profiles or
            sorted(timing['load_levels'])!=[0,2] or timing['environment_policy']!=DEFAULT_POLICY or
            set(timing['configurations'])!={'original','candidate','stock'}):raise RuntimeError('Predeclared workload/condition contract differs')
    baseline=linked(timing['baseline'])
    for name,item in timing['frozen_sources'].items():
        if sha256_file(Path(item['path']))!=item['sha256'] or sha256_file(ROOT/'scripts'/name)!=item['sha256']:
            raise RuntimeError('Measured implementation changed')
    quality=timing['quality'];q=linked(quality);source=Path(q['source_report'])
    if q['status']!='completed' or sha256_file(source)!=q['source_sha256'] or not all(v['quality_accepted'] for v in q['comparisons'].values()):
        raise RuntimeError('Full-frame quality evidence changed')
    if sha256_file(Path(quality['decoded_identity']))!=quality['decoded_identity_sha256']:
        raise RuntimeError('Decoded identity evidence changed')
    decoded=read(quality['decoded_identity']);qr=read(source)
    if (baseline['selection']['binaries']['ffmpeg']!=qr['configurations']['original'] or
            any(baseline['selection']['files'].get(p)!=v for p,v in qr['engine_files']['original'].items())):
        raise RuntimeError('Quality reference differs from the frozen baseline')
    if decoded['status']!='completed' or decoded['source_sha256']!=q['source_sha256'] or any(v['status']!='pass' for v in decoded['tests'].values()):
        raise RuntimeError('Decoded-frame identity failed')
    for item in decoded['decodes'].values():
        if sha256_file(Path(item['framehash']))!=item['sha256']:raise RuntimeError('Decoded framehash artifact changed')
    for item in q['quality'].values():
        if sha256_file(Path(item['report']))!=item['metric_sha256']:raise RuntimeError('Full-frame quality metric artifact changed')
    for item in timing['sources'].values():
        if sha256_file(Path(item['path']))!=item['sha256']:raise RuntimeError('Frozen source changed')
    log=Path(timing['directory'])/'admission.jsonl'
    if sha256_file(log)!=timing['admission_log_sha256']:raise RuntimeError('Admission evidence changed')
    runtime_binding(timing,qr,pipeline=pipeline)
    by_counter={r['counter']:r for r in timing['rows']};seen=set()
    for profile in profiles:
        if timing['specifications'][profile]!=qr['specifications'][profile]:raise RuntimeError('Quality workload differs')
        for load in (0,2):
            blocks=[b for b in timing['blocks'] if b['profile']==profile and b['load']==load and b['validation']['valid']]
            if len(blocks)!=9 or {b['block'] for b in blocks}!=set(range(9)):raise RuntimeError('Missing accepted whole blocks')
            rows=[]
            for block in blocks:
                values=[by_counter[name] for name in block['rows']];cache_proof(timing,values,profile);checked=[]
                for row in values:
                    counter=Path(row['counter']);data=read(counter)
                    if str(counter) in seen:raise RuntimeError('A timed process counter was reused')
                    seen.add(str(counter))
                    if (row['profile']!=profile or row['load']!=load or row['block']!=block['block'] or row['warmup'] or
                            sha256_file(counter)!=row['counter_sha256'] or row['seconds']!=data['process']['wall_seconds']):
                        raise RuntimeError('Elapsed time must match the actual kernel counter')
                    expected=next(r['sha256'] for r in qr['rows'] if r['profile']==profile and r['label']==row['label'])
                    if row['sha256']!=expected or sha256_file(Path(row['output']))!=expected:raise RuntimeError('Measured quality output changed')
                    environment=validate_case(data,load,DEFAULT_POLICY,pipeline=pipeline)
                    checked.append(dict(row,environment=environment))
                if not validate_block(checked,list(timing['configurations']),load,DEFAULT_POLICY,pipeline=pipeline)['valid']:
                    raise RuntimeError('Actual complete-block conditions failed')
                rows.extend(checked)
            for label in ('original','stock'):
                calculated=paired(rows,label);saved=analysis['comparisons'][profile+'/load'+str(load)][label]
                same=all(math.isclose(calculated[k],saved[k],rel_tol=1e-12,abs_tol=1e-12)
                    for k in ('paired_geometric_mean_ratio','candidate_median_seconds','reference_median_seconds'))
                same=same and all(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
                    for a,b in zip(calculated['whole_block_95_percent'],saved['whole_block_95_percent']))
                if not calculated['speedup_proven'] or not same:raise RuntimeError('Stored speed summary differs from actual counters')
    return timing,record(path)


def validate(value,files,active):
    if value.get('status')!='completed' or value.get('phase')!=11 or not value.get('release_performance_accepted'):
        raise RuntimeError('Complete Phase 11 performance acceptance required')
    if not {'direct_analysis','workflow_analysis','install_prefix','source_report','source_sha256'}<=set(value):
        raise RuntimeError('Combined direct and complete-workflow evidence required')
    direct_path=Path(value['direct_analysis']['path']);workflow_path=Path(value['workflow_analysis']['path'])
    linked(value['direct_analysis']);linked(value['workflow_analysis'])
    direct,_=audit(direct_path,pipeline=False);workflow,_=audit(workflow_path,pipeline=True)
    if direct['baseline']!=workflow['baseline']:raise RuntimeError('Direct and workflow baseline snapshots differ')
    source={Path(k).name:v for k,v in files.items() if k.startswith('ffv2/')}
    if workflow['package_source_sha256']!=source:raise RuntimeError('Workflow measured different SDK bytes')
    if workflow['quality']!=dict(direct['quality'],expected_output_sha256={'hd60':direct['quality']['expected_output_sha256']['hd60']}):
        raise RuntimeError('Direct and workflow quality evidence differ')
    if (value['source_report']!=str(Path(read(workflow_path)['source_report'])) or
            sha256_file(Path(value['source_report']))!=value['source_sha256']):raise RuntimeError('Workflow source binding differs')
    for timing in (direct,workflow):
        config=timing['configurations']['candidate'];binary=config['ffmpeg'] if timing.get('pipeline') else config
        if binary!=active['binaries']['ffmpeg']:raise RuntimeError('Different native candidate')
    if Path(value['install_prefix']).resolve()!=Path(active['install_prefix']).resolve():raise RuntimeError('Different native prefix')
    return True


def main():
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    parser=argparse.ArgumentParser();parser.add_argument('--direct-analysis',type=Path,required=True)
    parser.add_argument('--workflow-analysis',type=Path,required=True);parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise RuntimeError('Preserve completed performance evidence')
    candidate=read(args.candidate);workflow=read(args.workflow_analysis)
    value={'status':'completed','phase':11,'mode':'confirm','maintainer':'Jillur Rahman','release_performance_accepted':True,
        'install_prefix':candidate['prefix'],'source_report':workflow['source_report'],'source_sha256':workflow['source_sha256'],
        'direct_analysis':record(args.direct_analysis),'workflow_analysis':record(args.workflow_analysis),
        'scope':'Both references must be beaten in all four direct groups and both complete HD workflow load states; nine valid whole blocks each. Actual counters and quality bytes re-audited.'}
    validate(value,package_files(),{'install_prefix':candidate['prefix'],'binaries':candidate['binaries']})
    write_json(args.output,value);print(json.dumps({'performance':str(args.output),'accepted':True}))


if __name__=='__main__':main()
