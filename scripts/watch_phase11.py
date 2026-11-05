#!/usr/bin/python3 -B
"""Wait without encodes, then launch one unchanged, unmeasured confirmation."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from phase11_common import ROOT,WORK,read,freeze_sources
from admission_phase11 import wait_window
from conditions_phase11 import DEFAULT_POLICY
from ffv2.config import check_mounts
from ffv2.darwin import process_info
from ffv2.engine import library_closure,selection
from ffv2.io import sha256_file,write_json
from ffv2.resources import Policy,snapshot


def retryable(report):
    """A scheduling timeout may retry only before any measured case or block."""
    errors={'Automatic stable-window admission budget exhausted','Automatic CPU/disk admission budget exhausted'}
    return (report.get('phase')==11 and report.get('mode')=='confirm' and report.get('status')=='failed'
        and report.get('error') in errors and report.get('rows') is not None
        and all(row.get('warmup') is True for row in report['rows']) and report.get('blocks')==[]
        and report.get('required_valid_blocks')==9 and report.get('environment_policy')==DEFAULT_POLICY
        and set(report.get('specifications',{}))=={'hd60','raw30'} and report.get('load_levels')==[0,2]
        and all(held.get('status')!='active' for held in report.get('cache_holds',{}).values()))


def same_process(identity):
    value=process_info(identity['pid'])
    return bool(value and value['start_abstime']==identity['start_abstime'] and not value['exit_abstime'])


def same_content_closure(before,after):
    def content(files):
        return {name:{**row,'identity':{k:v for k,v in row['identity'].items() if k!='device'}} for name,row in files.items()}
    return content(before)==content(after)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--previous',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,required=True);parser.add_argument('--quality',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,default=WORK/'initial.json')
    parser.add_argument('--hours',type=int,choices=range(1,13),default=12);args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)));check_mounts(WORK)
    previous=read(args.previous)
    if not retryable(previous):raise RuntimeError('Only an entirely unmeasured scheduling timeout may retry')
    origin=read(WORK/'initial.json');baseline=read(args.baseline);recovery=args.baseline.resolve()!=(WORK/'initial.json').resolve()
    if recovery:
        if (baseline.get('origin_initial_sha256')!=sha256_file(WORK/'initial.json') or baseline['package_files']!=origin['package_files'] or
                baseline['selection']['binaries']!=origin['selection']['binaries'] or baseline['release']['version']!='0.6.0' or
                not same_content_closure(origin['selection']['files'],baseline['selection']['files'])):
            raise RuntimeError('Recovery baseline must preserve the original package and native content')
    directory=WORK/('window-watch-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700);target=directory/'report.json';continuation=WORK/'CONTINUATION.json'
    owner=process_info(os.getpid());identity={'pid':os.getpid(),'start_abstime':owner['start_abstime']}
    report={'status':'watching','phase':11,'directory':str(directory),'owner':identity,
        'previous_report':str(args.previous),'previous_sha256':sha256_file(args.previous),
        'candidate':str(args.candidate),'quality':str(args.quality),'source_sha256':sha256_file(Path(__file__)),
        'required_quiet_samples':30,'global_busy_max':6,'span_max':.75,'maximum_wait_hours':args.hours,
        'scope':'No mappings or encodes while waiting. Launch at most once, without importing previous warmups. Actual comparison gates unchanged.'}
    report['baseline']={'path':str(args.baseline),'sha256':sha256_file(args.baseline)}
    report['frozen_sources']=freeze_sources(directory,tuple(previous['frozen_sources']))
    if recovery:report['protocol_revision']='Explicit baseline snapshot after metadata-only mount recovery. Timing, argv, cache and validity gates unchanged; previous run has no measured cases.'
    def save():write_json(target,report)
    def register(**updates):
        state=read(continuation);state.update(updates);write_json(continuation,state)
    def bindings():
        if sha256_file(args.previous)!=report['previous_sha256'] or not retryable(read(args.previous)):
            raise RuntimeError('Previous unmeasured timeout changed')
        for name,item in previous['frozen_sources'].items():
            if sha256_file(Path(item['path']))!=item['sha256']:
                raise RuntimeError('Frozen benchmark method changed')
            if sha256_file(ROOT/'scripts'/name)!=report['frozen_sources'][name]['sha256']:
                raise RuntimeError('Prepared benchmark implementation changed')
            if sha256_file(ROOT/'scripts'/name)!=item['sha256'] and (not recovery or name!='benchmark_phase11.py'):
                raise RuntimeError('Only the explicit baseline argument may differ after mount recovery')
        if not recovery and sha256_file(args.quality)!=previous['quality']['sha256']:
            raise RuntimeError('Frozen quality evidence changed')
        quality=read(args.quality);qr=read(Path(quality['source_report']));candidate=read(args.candidate)
        if (sha256_file(args.candidate)!=qr['candidate_manifest_sha256'] or candidate.get('profile_instrumented') or
                qr['configurations']!=previous['configurations'] or qr['specifications']!=previous['specifications'] or
                any(not same_content_closure(previous['engine_files'][label],qr['engine_files'][label]) for label in previous['configurations'])):
            raise RuntimeError('Candidate/quality binding changed')
        if quality['status']!='completed' or not all(v['quality_accepted'] for v in quality['comparisons'].values()):raise RuntimeError('Fresh quality failed')
        if sha256_file(Path(quality['source_report']))!=quality['source_sha256']:raise RuntimeError('Quality source changed')
        identity=read(args.quality.with_name('decoded-identity.json'))
        if identity['status']!='completed' or identity['source_sha256']!=quality['source_sha256']:raise RuntimeError('Fresh decoded identity required')
        for row in qr['rows']:
            if row['sha256']!=previous['quality']['expected_output_sha256'][row['profile']][row['label']]:raise RuntimeError('Quality output changed after mount recovery')
        selected=selection(verify_hashes=True)
        if selected['selection_id']!=baseline['selection']['selection_id'] or sha256_file(args.baseline)!=report['baseline']['sha256']:
            raise RuntimeError('Active baseline changed')
        for label,binary in previous['configurations'].items():
            if library_closure([Path(binary)])!=qr['engine_files'][label]:raise RuntimeError('Runtime closure changed')
        return qr
    policy=Policy();images=set().union(*(set(c) for c in previous['engine_files'].values()))
    reserve=max(Path(v['path']).stat().st_size for v in previous['sources'].values())+sum(Path(p).stat().st_size for p in images)+2*1024**3
    def ready():
        check_mounts(directory);current=snapshot(directory)
        reasons=policy.admission(current,8*1024**3,8*1024**3)
        if policy.boot_used_limit is not None and current.boot_used_bytes+reserve>=policy.boot_used_limit:reasons.append('boot_disk_cache_reserve')
        return {'ready':not reasons,'reasons':reasons,'boot_used_bytes':current.boot_used_bytes,'reserved_bytes':reserve}
    child=None;discovered=None;started=time.monotonic()
    try:
        current_quality=bindings();save()
        quality_link=dict(previous['quality'],path=str(args.quality),sha256=sha256_file(args.quality),
            decoded_identity=str(args.quality.with_name('decoded-identity.json')),
            decoded_identity_sha256=sha256_file(args.quality.with_name('decoded-identity.json')))
        state=read(continuation);old=state.get('window_watch')
        if old and same_process(old['owner']):raise RuntimeError('An owned window watcher is already alive')
        register(status='Waiting for quiet CPU; previous run had no measured cases',window_watch={'report':str(target),'owner':identity},
            live={'status':'waiting_for_quiet_cpu','previous_status':'failed_admission_budget','measured_cases':0,'accepted_blocks':0})
        while time.monotonic()-started<args.hours*3600:
            remaining=args.hours*3600-(time.monotonic()-started)
            try:
                admitted=wait_window(directory/'admission.jsonl','replacement-confirmation',timeout=min(50,remaining),
                    required=30,probe_after=float('inf'),admit=ready)
            except RuntimeError as error:
                if str(error)!='Automatic stable-window admission budget exhausted':raise
                report['wait_seconds']=time.monotonic()-started;save();continue
            report['admission']=admitted;bindings()
            if not ready()['ready']:continue
            known=set(WORK.glob('confirm-*/report.json'))
            command=[sys.executable,'-B',str(ROOT/'scripts/benchmark_phase11.py'),'--mode','confirm',
                '--candidate',str(args.candidate),'--quality',str(args.quality),'--baseline',str(args.baseline),'--blocks','9','--max-attempts','45']
            environment=os.environ.copy();environment['FFV2_IGNORE_SYSTEM_MEMORY']='1'
            with (directory/'benchmark.stdout.log').open('xb') as out,(directory/'benchmark.stderr.log').open('xb') as err:
                child=subprocess.Popen(command,cwd=ROOT.parent,env=environment,stdout=out,stderr=err,start_new_session=True)
            for _ in range(50):
                value=process_info(child.pid)
                if value:break
                if child.poll() is not None:raise RuntimeError('Benchmark exited before process registration')
                time.sleep(.01)
            if not value:raise RuntimeError('Owned benchmark birth unavailable')
            born={'pid':child.pid,'start_abstime':value['start_abstime']}
            report.update(status='benchmark_running',benchmark_owner=born,command=command);save()
            register(status='Replacement confirmation starting after quiet CPU admission',benchmark_owner=born,
                pending_benchmark_report=True)
            while child.poll() is None:
                if discovered is None:
                    new=set(WORK.glob('confirm-*/report.json'))-known
                    if len(new)>1:raise RuntimeError('Ambiguous new confirmation report')
                    if new:
                        discovered=next(iter(new));new_report=read(discovered)
                        if (new_report['configurations']!=previous['configurations'] or new_report['quality']!=quality_link or
                                new_report['engine_files']!=current_quality['engine_files'] or new_report['baseline']!=report['baseline'] or
                                new_report['environment_policy']!=previous['environment_policy']):raise RuntimeError('Replacement contract differs')
                        report['benchmark_report']=str(discovered);save()
                        state=read(continuation);history=state.get('previous_benchmark_reports',[])
                        if str(args.previous) not in history:history.append(str(args.previous))
                        register(status='Conditioned replacement acceptance running; no promotion',benchmark_report=str(discovered),
                            benchmark_tool_session=None,pending_benchmark_report=False,previous_benchmark_reports=history,
                            live={'status':'running','warmup_cases':0,'measured_cases':0,'accepted_blocks':0})
                time.sleep(.5)
            report.update(status='benchmark_finished',benchmark_exit_code=child.returncode)
            if discovered is None:raise RuntimeError('Benchmark did not publish a report')
            report['benchmark_status']=read(discovered)['status'];save();return
        report.update(status='waiting_budget_exhausted',wait_seconds=time.monotonic()-started);save()
    except BaseException as error:
        report.update(status='failed',error=str(error)[:4000])
        if child and child.poll() is None:
            report['owned_benchmark_left_supervised']=True
        save();raise
    finally:save()


if __name__=='__main__':main()
