#!/usr/bin/python3 -B
"""Cold evidence validation, portable index and post-commit completion audit."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
from pathlib import Path
import statistics
import platform
import sqlite3
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase8')))
INDEX=ROOT/'docs/verification/phase8-2026-11-04.json'
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection
from ffv2.io import sha256_file,write_json
from ffv2.releases import ACTIVE,package_files,verified


def read(path):
    return json.loads(Path(path).read_text())


def completed(path):
    value=read(path)
    if value['status']!='completed':
        raise RuntimeError('Completed evidence required: '+str(path))
    tests=value.get('tests',{})
    if any(row['status']!='pass' for row in tests.values()):
        raise RuntimeError('Non-passing evidence record: '+str(path))
    return value


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--lifecycle',type=Path)
    parser.add_argument('--mcp',type=Path)
    parser.add_argument('--source-default',type=Path)
    parser.add_argument('--installed-default',type=Path)
    parser.add_argument('--installed-consumer',type=Path)
    parser.add_argument('--isolation',type=Path)
    parser.add_argument('--configuration',type=Path)
    parser.add_argument('--audit',action='store_true')
    args=parser.parse_args()
    active=read(ACTIVE)
    manifest=verified(Path(active['manifest']))
    if active['version']!='0.6.0' or manifest['package_files']!=package_files():
        raise RuntimeError('Frozen final 0.6.0 source/installed pair required')
    selected=selection(path=Path(active['manifest']).parent/'engine.json',verify_hashes=True)
    if len(selected['files'])!=38:
        raise RuntimeError('Expected unchanged native closure')
    if args.audit:
        value=completed(INDEX)
        if value['release_id']!=active['release_id']:
            raise RuntimeError('Portable index targets a different release')
        for record in value['evidence'].values():
            if sha256_file(Path(record['path']))!=record['sha256']:
                raise RuntimeError('Indexed evidence changed')
        status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True)
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        tag=subprocess.check_output(['git','rev-parse','v0.6.0^{commit}'],cwd=ROOT,text=True).strip()
        if status or tag!=commit:
            raise RuntimeError('Clean final source and matching v0.6.0 tag required')
        author=subprocess.check_output(['git','show','-s','--format=%an <%ae>|%cn <%ce>'],cwd=ROOT,text=True).strip()
        owner='Jillur Rahman <22579419+developerjillur@users.noreply.github.com>'
        if author!=owner+'|'+owner:
            raise RuntimeError('Sole maintainer attribution mismatch')
        databases={ROOT/'.runtime/jobs.sqlite3',*WORK.rglob('jobs.sqlite3')}
        for name,record in value['evidence'].items():
            if name=='mcp' or name.startswith('preinstall_supplement_'):
                directory=read(record['path']).get('directory')
                if directory:
                    databases.update(Path(directory).rglob('jobs.sqlite3'))
        active_jobs=0
        for database in databases:
            if not database.exists():
                continue
            db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
            try:
                active_jobs+=db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','waiting_resources','running','validating')").fetchone()[0]
            finally:
                db.close()
        if active_jobs:
            raise RuntimeError('Owned evidence/default queues still contain active jobs')
        post_index={}
        for name in ('calibration-source-reconstruction.json','fault-ledger-recovery.json'):
            path=WORK/name
            completed(path)
            post_index[name]={'path':str(path),'sha256':sha256_file(path)}
        target=WORK/'completion-audit-v0.6.0.json'
        if target.exists():
            raise RuntimeError('Retain previous audit')
        write_json(target,{'status':'completed','maintainer':'Jillur Rahman','audited_at':time.time(),
            'version':'0.6.0','release_id':active['release_id'],'git_commit':commit,'git_tag':'v0.6.0',
            'git_worktree_clean':True,'index':str(INDEX),'index_sha256':sha256_file(INDEX),
            'results_sha256':sha256_file(ROOT/'docs/PHASE8-RESULTS.md'),'requirements':value['requirements'],
            'package_files':len(package_files()),'native_files':len(selected['files']),
            'checked_job_databases':len(databases),'active_default_and_task_jobs':active_jobs,
            'post_index_receipts':post_index})
        print(json.dumps({'audit':str(target),'requirements':len(value['requirements']),'commit':commit}))
        return
    if INDEX.exists() or any(getattr(args,key) is None for key in
            ('lifecycle','mcp','source_default','installed_default','installed_consumer','isolation','configuration')):
        raise RuntimeError('New index and all fresh lifecycle/integration receipts required')
    life=completed(args.lifecycle)
    if life['final']['release_id']!=active['release_id'] or len(life['tests'])!=10 or life['previous_stable']['version']!='0.5.0':
        raise RuntimeError('Actual update/recovery and retained stable release proof required')
    previous=read(active['previous'])
    if previous['version']!='0.5.0':
        raise RuntimeError('Default rollback must restore stable 0.5.0')
    acceptance_path=Path(life['final_acceptance'])
    acceptance=completed(acceptance_path)
    if acceptance['package_files']!=package_files():
        raise RuntimeError('Final acceptance source mismatch')
    paths={name:Path(row['path']) for name,row in acceptance['gates'].items()}
    paths.update(lifecycle=args.lifecycle,mcp=args.mcp,source_default=args.source_default,
                 installed_default=args.installed_default,installed_consumer=args.installed_consumer,
                 acceptance=acceptance_path,diagnostics=WORK/'diagnostics.json',
                 isolation=args.isolation,
                 configuration=args.configuration,
                 calibration=WORK/'calibrate-20261103T180018-a55648e2/analysis.json')
    for index,row in enumerate(acceptance.get('supplements',[])):
        path=Path(row['path'])
        if sha256_file(path)!=row['sha256']:
            raise RuntimeError('Pre-install supplement changed')
        if path not in paths.values():
            paths['preinstall_supplement_'+str(index)]=path
    evidence={}
    reports={}
    for name,path in paths.items():
        reports[name]=completed(path)
        evidence[name]={'path':str(path.resolve()),'sha256':sha256_file(path)}
        if name in acceptance['gates'] and evidence[name]['sha256']!=acceptance['gates'][name]['sha256']:
            raise RuntimeError('Accepted evidence changed: '+name)
    perf=reports['performance']
    if not perf['release_performance_accepted'] or perf['mode']!='confirm':
        raise RuntimeError('Independent speed/quality acceptance missing')
    timing_path=Path(perf['source_report']);quality_path=Path(perf['quality_report'])
    if sha256_file(timing_path)!=perf['source_sha256'] or sha256_file(quality_path)!=perf['quality_sha256']:
        raise RuntimeError('Performance sub-evidence changed')
    timing=read(timing_path);qualities=completed(quality_path)
    bindings=read(WORK/'initial-bindings.json')
    for path,record in bindings['stock_files'].items():
        if sha256_file(Path(path))!=record['sha256'] or any(Path(alias).resolve()!=Path(path) for alias in record['load_paths']):
            raise RuntimeError('Stock binary/dependency identity changed')
    for label in timing['configurations']:
        rows=[row for row in timing['cases'] if row['label']==label]
        if len({row['runtime_binding_id'] for row in rows})!=1 or not rows[0]['runtime_binding_id']:
            raise RuntimeError('Measured binary closure changed within a comparator')
    for key,path in (('timing',timing_path),('quality',quality_path)):
        evidence[key]={'path':str(path),'sha256':sha256_file(path)}
    for source in timing['profiles'].values():
        if sha256_file(Path(source['input']))!=source['source_sha256']:
            raise RuntimeError('Reference corpus changed')
    peaks={}
    decoded_frames=0
    for profile in timing['profiles']:
        for label in timing['configurations']:
            values=[]
            for row in timing['cases']:
                if row['profile']!=profile or row['label']!=label:
                    continue
                if sha256_file(Path(row['output']))!=row['sha256']:
                    raise RuntimeError('Measured output changed')
                receipt=read(row['receipt'])
                decoded_frames+=int(receipt['validation']['full_decode']['last_progress']['frame'])
                if not row['warmup']:
                    values.append(max(receipt['encoding']['peak_job_memory_bytes'],receipt['validation']['full_decode']['peak_job_memory_bytes']))
            peaks[profile+'/'+label]={'median_bytes':statistics.median(values),'maximum_bytes':max(values)}
    for record in qualities['quality'].values():
        if sha256_file(Path(record['report']))!=record['metric_sha256']:
            raise RuntimeError('Full-frame metric changed')
    for name in ('source_default','installed_default'):
        checks=reports[name]['checks']
        if set(checks)!={'bbb-1080','tos-liveaction','bbb-2160','bbb-2160-to1080'}:
            raise RuntimeError('Four actual CLI defaults required')
        for row in checks.values():
            if row['status']!='pass' or sha256_file(Path(row['output']))!=row['output_sha256']:
                raise RuntimeError('CLI published output changed')
    mcp=reports['mcp']
    if mcp['server_info']['version']!='0.6.0' or mcp['checks']['bounded_software_threads8']['status']!='pass':
        raise RuntimeError('Fresh configured final MCP/threads8 proof required')
    config=reports['configuration']
    if (config['changed'] or not config['verify_only'] or config['installed_version']!='0.6.0' or
            config['before_sha256']!=config['after_sha256'] or sha256_file(Path(config['config']))!=config['after_sha256']):
        raise RuntimeError('Existing client configuration must remain byte-identical')
    unit=reports['unit_tests']
    if unit['package_files']!=package_files() or len(unit['runs'])!=2 or any(r['tests']<131 or r['exit_code'] for r in unit['runs']):
        raise RuntimeError('Final two-runtime regression missing')
    requirements=[{'requirement':str(i+1),'status':'pass','description':description,'evidence':keys}
        for i,(description,keys) in enumerate([
            ('Stage diagnosis and uncertainty; same x264/native compiler/owned CPU sample and adjacent stage-pair proof',['diagnostics','isolation']),
            ('Sequential seven-configuration calibration and full-frame quality/size gates',['calibration']),
            ('Independent nine-pair improvement against prior native and Stock presets; matched Stock control disclosed',['performance','quality','timing']),
            ('Scoped defaults, explicit/other-pipeline regression, actual UHD and resize output identity',['unit_tests','source_default','installed_default']),
            ('Actual advanced/recovery/Studio and configured MCP including bounded eight-thread transcode',['phase5','checkpoint','consumer','installed_consumer','mcp']),
            ('Immutable 0.6.0 update/fences/rollback/recovery and retained 0.5.0 stable pair',['lifecycle','acceptance'])])]
    value={'schema_version':1,'status':'completed','maintainer':'Jillur Rahman','created_at':time.time(),
        'version':'0.6.0','release_id':active['release_id'],'git_ref':'v0.6.0','package_files':package_files(),
        'engine_selection_id':selected['selection_id'],'native_files':len(selected['files']),
        'evidence':evidence,'requirements':requirements,'unit_runs':unit['runs'],'comparisons':perf['comparisons'],
        'summary':timing['summary'],'quality':qualities['quality'],'sampled_job_peak':peaks,
        'fresh_case_process_wall_medians':{profile+'/'+label:statistics.median(r['process_wall_seconds'] for r in timing['cases']
            if r['profile']==profile and r['label']==label and not r['warmup']) for profile in timing['profiles'] for label in timing['configurations']},
        'post_run_live_environment':{'python_executable':sys.executable,'python_version':platform.python_version(),
            'macos_version':platform.mac_ver()[0],'system':platform.system(),'machine':platform.machine(),'kernel_release':platform.release()},
        'version_transition':acceptance['version_transition'],
        'coverage':{'calibration_complete_jobs':56,'confirmation_complete_jobs':len(timing['cases']),
                    'confirmation_measured_jobs':sum(not r['warmup'] for r in timing['cases']),
                    'confirmation_actual_decoded_frames':decoded_frames,
                    'adjacent_diagnostic_jobs':len(reports['isolation']['rows']),
                    'lifecycle_actual_cases':len(life['tests']),'installed_cli_defaults':4},
        'scope':'Phase 8 HD/live-action workflow policy; unchanged native core and retained binary/FATE/soak gates identified by original paths. Newly matched Stock is a control, not a claim of core superiority. Media memory waiver is invocation-scoped; sampled job/disk/mount/deadline/output guards remain.'}
    write_json(INDEX,value)
    print(json.dumps({'index':str(INDEX),'requirements':len(requirements),'release_id':active['release_id']}))


if __name__=='__main__':
    main()
