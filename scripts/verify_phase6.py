#!/usr/bin/python3 -B
"""বাস্তব segment retry, preemption, process loss ও elapsed-time soak।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from verify_phase5 import Check
from ffv2.config import Settings
from ffv2.darwin import process_info
from ffv2.errors import FFV2Error
from ffv2.io import capture, sha256_file, write_json
from ffv2.planner import build_plan
from ffv2.store import Store
from ffv2.worker import host_lock, work

ROOT = Path(__file__).resolve().parents[1]
CORPUS = Path(str(lab_path('ffmpeg-v2-phase4/corpus')))

def wait_for(predicate, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.02)
    raise RuntimeError('Verification condition timed out')

def active_registration(directory):
    for path in directory.glob('state/jobs/*/attempt-*/*.request.live.json'):
        if path.with_suffix('.guardian-ready.json').exists():
            value = json.loads(path.read_text())
            info = process_info(value['pid'])
            if info and not info['exit_abstime'] and info['start_abstime'] == value['start_abstime']:
                return path, value
    return None

def worker(settings, job_id=None, drain=False):
    command = [sys.executable, '-B', str(ROOT / 'bin/ffv2'), '--ignore-system-memory', '--state-dir', str(settings.state), 'worker']
    if job_id:
        command += ['--job-id', job_id]
    if drain:
        command += ['--drain']
    log = settings.state.parent / ('worker-' + uuid.uuid4().hex[:8] + '.log')
    with log.open('xb') as out:
        child = subprocess.Popen(command, stdout=out, stderr=out, env=os.environ.copy())
    return child, log

def quick(verify, retained_source=None):
    d, binary = verify.directory, verify.caps['ffmpeg']
    source = retained_source or d / 'real-cfr.mkv'
    if not retained_source:
        verify.aux('real-source', [binary, '-v', 'error', '-nostdin', '-n', '-filter_threads', '2', '-threads', '2', '-ss', '60', '-i', str(CORPUS/'bbb-1080.mp4'),
            '-t', '120', '-vf', 'scale=640:360,setsar=1', '-r', '30', '-fps_mode', 'cfr', '-c:v', 'ffv1', '-threads:v', '2', '-c:a', 'pcm_s16le', '-threads:a', '1', '-fs', str(512*1024**2), str(source)], source, timeout=180, budget=512*1024**2)
    spec = {'operation': 'transcode', 'input': str(source), 'output': str(d/'resumed.mp4'), 'encoder': 'software', 'fps': 30, 'duration': 120,
            'checkpoint_seconds': 10, 'threads': 1, 'priority': -5, 'timeout_seconds': 600}
    plan = build_plan(spec, verify.settings, verify.caps)
    queued = verify.store.enqueue(plan)
    # Explicit binaries keep the test independent of active-engine promotion.
    environment = {**os.environ, 'FFV2_FFMPEG': binary, 'FFV2_FFPROBE': verify.caps['ffprobe']}
    previous = {k: os.environ.get(k) for k in ('FFV2_FFMPEG', 'FFV2_FFPROBE')}
    os.environ.update({k:environment[k] for k in previous})
    try:
        child, log = worker(verify.settings, queued['id'])
        checkpoint = verify.store.root/'jobs'/queued['id']/'checkpoints/manifest.json'
        def two_segments():
            if child.poll() is not None:
                raise RuntimeError('Checkpoint worker stopped: ' + log.read_text()[-2500:])
            if checkpoint.exists():
                value = json.loads(checkpoint.read_text())
                return value if len(value['segments']) >= 2 else None
        saved = wait_for(two_segments, 120)
        registration = wait_for(lambda: active_registration(d), 10)[1]
        if registration['worker_pid'] != child.pid:
            raise RuntimeError('Unexpected checkpoint worker identity')
        child.kill()
        child.wait(timeout=10)
        wait_for(lambda: not process_info(registration['pid']) or process_info(registration['pid'])['exit_abstime'], 10)
        def recover_when_unlocked():
            try:
                with host_lock(verify.settings):
                    verify.store.recover()
                return True
            except FFV2Error as error:
                if error.code != 'worker_busy':
                    raise
                return False
        wait_for(recover_when_unlocked, 15)
        if Path(spec['output']).exists():
            raise RuntimeError('Interrupted job published a final output')
        # Replace exactly one task-created checkpoint inode. Original validated
        # staging link remains as rollback evidence; no user source is modified.
        damaged = Path(saved['segments']['1']['path'])
        print(json.dumps({'affected_test_checkpoint': str(damaged)}), flush=True)
        replacement = damaged.with_suffix('.corrupt-test')
        replacement.write_bytes(b'corrupt checkpoint fixture')
        os.replace(replacement, damaged)
        verify.store.retry(queued['id'])
        urgent = verify.store.enqueue(build_plan({'operation': 'frame', 'input': str(source), 'output': str(d/'urgent.jpg'), 'start': 1, 'priority': 10}, verify.settings, verify.caps))
        # Low job is selected explicitly once; it must yield at a durable boundary.
        work(verify.settings, job_id=queued['id'])
        if verify.store.get(queued['id'], plan=False)['status'] != 'queued':
            raise RuntimeError('Checkpoint boundary did not yield to higher priority')
        outcome = work(verify.settings, drain=True)
        final = verify.store.get(queued['id'], plan=False)
        if final['status'] != 'completed' or verify.store.get(urgent['id'], plan=False)['status'] != 'completed':
            raise RuntimeError('Retry/preemption failed: ' + str(outcome))
        cp = final['receipt']['checkpoints']
        manifest = json.loads(checkpoint.read_text())
        if 0 not in cp['reused_segments'] or not manifest['invalidated'] or sha256_file(Path(saved['segments']['0']['path'])) != saved['segments']['0']['sha256']:
            raise RuntimeError('Validated reuse/corruption recovery did not occur')
        times = verify.frame_times(Path(spec['output']))
        if len(times) != 3600 or max(abs(t-i/30) for i,t in enumerate(times)) > .0011:
            raise RuntimeError('Recovered final frame grid/count')
        def packets(path):
            code, text, err = capture([verify.caps['ffprobe'], '-v', 'error', '-select_streams', 'a:0', '-show_packets', '-show_data_hash', 'sha256', '-show_entries', 'packet=data_hash', '-of', 'json', str(path)], timeout=60)
            if code:
                raise RuntimeError(err[-1000:])
            return [p['data_hash'] for p in json.loads(text)['packets']]
        if packets(spec['output']) != packets(cp['continuous_audio']):
            raise RuntimeError('Final mux changed or dropped continuous audio packets')
        verify.passed('checkpoint_interrupt_corruption_preemption', frames=len(times), attempt=final['attempt'], reused_segments=cp['reused_segments'],
                      invalidated=len(manifest['invalidated']), continuous_audio_packets_equal=True, receipt=final['receipt']['directory'])
        # Persist the exact post-link/pre-database crash state, then reconcile it.
        verify.store.update(queued['id'], 'validating')
        with host_lock(verify.settings):
            verify.store.recover()
        recovered = verify.store.get(queued['id'], plan=False)
        if recovered['status'] != 'completed' or not recovered['receipt'].get('reconciled_publish'):
            raise RuntimeError('Validated published-output reconciliation failed')
        verify.passed('published_output_reconciliation', method='persisted-state injection after actual validated publication', sha256=recovered['receipt']['output_sha256'])
    finally:
        if 'child' in locals() and child.poll() is None:
            child.terminate()
            child.wait(timeout=10)
        for key,value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    # Actual output-directory write denial, followed by an explicit retry.
    denied = d/'write-denied'
    denied.mkdir()
    denied.chmod(0o500)
    try:
        failed = verify.media('write-denied', {'operation': 'frame', 'input': str(source), 'output': str(denied/'frame.jpg')}, failed=True)
    finally:
        denied.chmod(0o700)
    verify.store.retry(failed['id'])
    work(verify.settings, job_id=failed['id'])
    if verify.store.get(failed['id'], plan=False)['status'] != 'completed':
        raise RuntimeError('Filesystem denial retry failed')
    verify.passed('filesystem_write_error_retry', initial_code=failed['error']['code'])
    for mode in ('worker-kill', 'supervisor-kill', 'both-kill', 'cancel', 'timeout'):
        area = d/mode
        area.mkdir()
        log = area/'helper.log'
        with log.open('xb') as out:
            child = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--prefix', str(verify.prefix), '--directory', str(area), '--helper', mode, '--source', str(source)], stdout=out, stderr=out, env=os.environ.copy())
        _, registered = wait_for(lambda: active_registration(area), 20)
        info = process_info(registered['pid'])
        if not info or info['start_abstime'] != registered['start_abstime'] or registered['worker_pid'] != child.pid:
            raise RuntimeError('Failure helper ownership mismatch')
        if mode in ('supervisor-kill', 'both-kill'):
            os.kill(registered['supervisor_pid'], signal.SIGKILL)
        if mode in ('worker-kill', 'both-kill'):
            child.kill()
        if mode == 'cancel':
            request = next(area.glob('state/jobs/*/attempt-*/fault.request.json'))
            job = json.loads(request.read_text())
            Store(Settings(state=area/'state')).cancel(job['job_id'])
        child.wait(timeout=15)
        wait_for(lambda: not process_info(registered['pid']) or process_info(registered['pid'])['exit_abstime'], 10)
        wait_for(lambda: next(area.glob('state/jobs/*/attempt-*/*.guardian-receipt.json'), None), 10)
        verify.passed(mode, helper_exit=child.returncode, media_stopped=True, birth_identity=registered['start_abstime'])

def soak(verify, seconds):
    d, binary = verify.directory, verify.caps['ffmpeg']
    output = d/'realtime-real-media.mp4'
    started = time.monotonic()
    receipt = verify.aux('elapsed-soak', [binary, '-v', 'error', '-nostdin', '-n', '-nostats', '-progress', 'pipe:1', '-progress_format', 'jsonl',
        '-filter_threads', '1', '-readrate', '1', '-stream_loop', '-1', '-threads', '2', '-i', str(CORPUS/'bbb-1080.mp4'), '-t', str(seconds),
        '-vf', 'scale=640:360,setsar=1', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-threads:v', '2', '-c:a', 'aac', '-threads:a', '1', '-b:a', '128k',
        '-movflags', '+faststart', '-fs', str(2*1024**3), str(output)], output, timeout=seconds+180, budget=2*1024**3)
    elapsed = time.monotonic()-started
    if elapsed < seconds-3:
        raise RuntimeError('Soak was not a real elapsed-time run')
    verified = verify.media('soak-remux-full-validation', {'operation': 'remux', 'input': str(output), 'output': str(d/'soak-validated.mkv'), 'timeout_seconds': 600})
    final_validation = verified['receipt']['validation']
    frames = int(final_validation['full_decode']['last_progress']['frame'])
    if frames != seconds*30 or abs(final_validation['metadata']['duration_seconds']-seconds) > .05:
        raise RuntimeError('Soak output frame count/A/V endpoint mismatch')
    trace = Path(receipt['resource_trace']['path'])
    records = [json.loads(line) for line in trace.read_text().splitlines()]
    if len(records) < seconds//6 or records[-1]['elapsed_seconds'] < seconds-8:
        raise RuntimeError('Complete sampled resource trace is missing')
    verify.passed('elapsed_real_media_soak', elapsed_seconds=elapsed, media_seconds=seconds, resource_records=len(records),
        trace=receipt['resource_trace'], peak_job_memory_bytes=receipt['peak_job_memory_bytes'], output_sha256=sha256_file(output),
        full_decode=verified['receipt']['validation']['full_decode']['status'],frames=frames,
        duration_seconds=final_validation['metadata']['duration_seconds'],limitation='Bounded 30-minute local soak; not an overnight or every-format guarantee')

def batch(verify):
    profiles = [('real-hd','bbb-1080.mp4',1920,1080,30,180),
                ('real-uhd','bbb-2160.mp4',3840,2160,30,180),
                ('real-liveaction','tos-1080-blender.webm',1920,800,24,180)]
    jobs=[]
    for name,source,width,height,fps,seconds in profiles:
        spec={'operation':'transcode','input':str(CORPUS/source),'output':str(verify.directory/(name+'.mp4')),
              'encoder':'software','fps':fps,'start':60,'duration':seconds,'max_width':width,'max_height':height,'timeout_seconds':1200}
        plan=build_plan(spec,verify.settings,verify.caps)
        queued=verify.store.enqueue(plan,key=name)
        replay=verify.store.enqueue(plan,key=name)
        if replay['id']!=queued['id'] or not replay['replayed']:
            raise RuntimeError('Batch idempotency replay failed')
        jobs.append((queued['id'],name,fps*seconds))
    started=time.monotonic()
    outcome=work(verify.settings,drain=True)
    if outcome['processed']!=3 or outcome['completed']!=3:
        raise RuntimeError('Real media batch failed: '+str(outcome))
    outputs=[]
    for identity,name,frames in jobs:
        result=verify.store.get(identity,plan=False)
        receipt=result['receipt']
        if int(receipt['validation']['full_decode']['last_progress']['frame'])!=frames:
            raise RuntimeError('Real batch output frame count mismatch')
        outputs.append({'profile':name,'frames':frames,'sha256':receipt['output_sha256'],'receipt':str(Path(receipt['directory'])/'receipt.json'),
                        'runtime_tuning':receipt['runtime_tuning'],'phase_timings_seconds':receipt['phase_timings_seconds']})
    verify.passed('real_hd_uhd_liveaction_batch',elapsed_seconds=time.monotonic()-started,total_media_seconds=540,
        idempotency_verified=True,sequential=True,outputs=outputs)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', required=True, type=Path)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--mode', choices=('quick','soak','batch'), default='quick')
    parser.add_argument('--soak-seconds', type=int, choices=(1800,3600), default=1800)
    parser.add_argument('--helper', choices=('worker-kill','supervisor-kill','both-kill','cancel','timeout'))
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    directory = args.directory or Path(str(lab_path('ffmpeg-v2-phase6')))/(args.mode+'-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    verify = Check(args.prefix.resolve(strict=True), directory)
    if args.helper:
        output = directory/'partial.mp4'
        verify.aux('fault', [verify.caps['ffmpeg'], '-v', 'error', '-nostdin', '-n', '-nostats', '-progress', 'pipe:1', '-stats_period', '.1', '-readrate', '1',
            '-threads', '1', '-i', str(args.source), '-t', '60', '-vf', 'scale=160:90', '-filter_threads', '1', '-c:v', 'libx264', '-preset', 'veryfast', '-threads:v', '1',
            '-an', '-fs', str(16*1024**2), str(output)], output, timeout=1 if args.helper=='timeout' else 80, budget=16*1024**2)
        raise RuntimeError('Fault helper unexpectedly completed')
    verify.report['script_sha256'] = sha256_file(Path(__file__))
    try:
        if args.mode=='quick':quick(verify,args.source)
        elif args.mode=='batch':batch(verify)
        else:soak(verify,args.soak_seconds)
        verify.report['status'] = 'completed'
    except BaseException as error:
        verify.report.update(status='failed',error=str(error)[:6000])
        raise
    finally:
        verify.save()
    print(json.dumps({'report':str(directory/'report.json'),'checks':len(verify.report['tests'])}))

if __name__=='__main__':
    main()
