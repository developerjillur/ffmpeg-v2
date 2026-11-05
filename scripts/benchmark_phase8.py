#!/usr/bin/python3 -B
"""Frozen software calibration, sampled warmups ও same-quality confirmation।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(str(lab_path('ffmpeg-v2-phase8')))
BASELINE = WORK/'baseline'
PREVIOUS = Path(str(lab_path('ffmpeg-v2-phase4/acceptance-20261103T170546-0cf42211/report.json')))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', help=argparse.SUPPRESS)
    parser.add_argument('--mode', choices=('calibrate', 'confirm'), default='calibrate')
    parser.add_argument('--trials', type=int, choices=(3, 5, 7, 9), default=3)
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--profile', action='append', choices=('bbb-1080', 'tos-liveaction'))
    args = parser.parse_args()
    if args.case:
        import contextlib
        import io
        from benchmark_phase2 import case
        request = json.loads(args.case)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = case(request)
        value = json.loads(output.getvalue())
        plan = json.loads((Path(value['receipt']).parent/'plan.json').read_text())
        value.update(runtime_tuning=plan['runtime_tuning'], runtime_code_id=plan.get('runtime_code_id'),
                     runtime_binding_id=plan['binary'].get('runtime_binding', {}).get('binding_id'))
        print(json.dumps(value))
        return result
    sys.path.insert(0, str(ROOT))
    from ffv2.config import check_mounts
    from ffv2.darwin import process_info
    from ffv2.engine import selection
    from ffv2.io import sha256_file, write_json
    from ffv2.resources import Policy, snapshot
    inherited_nice = os.getpriority(os.PRIO_PROCESS, 0)
    if inherited_nice < 10:
        os.nice(10-inherited_nice)
    job_nice = os.getpriority(os.PRIO_PROCESS, 0)
    selected = selection(verify_hashes=True)
    previous = json.loads(PREVIOUS.read_text())
    profiles = {name: previous['profiles'][name] for name in args.profile or ('bbb-1080', 'tos-liveaction')}
    for profile in profiles.values():
        if sha256_file(Path(profile['input'])) != profile['source_sha256']:
            raise RuntimeError('Production source changed')
    configurations = {
        'native4': {'package': str(BASELINE), 'threads': 4, 'decoder_threads': 2, 'filter_threads': 2, 'validation_threads': 4},
        'native6': {'package': str(ROOT), 'threads': 6, 'decoder_threads': 2, 'filter_threads': 2, 'validation_threads': 4},
        'native8': {'package': str(ROOT), 'threads': 8, 'decoder_threads': 2, 'filter_threads': 2, 'validation_threads': 4},
        'native8-lean': {'package': str(ROOT), 'threads': 8, 'decoder_threads': 1, 'filter_threads': 1, 'validation_threads': 4},
        'native8-validation8': {'package': str(ROOT), 'threads': 8, 'decoder_threads': 2, 'filter_threads': 2, 'validation_threads': 8},
        'stock4': {'package': str(BASELINE), 'engine': 'stock', 'threads': 4, 'decoder_threads': 2, 'filter_threads': 2, 'validation_threads': 4},
        'stock8': {'package': str(ROOT), 'engine': 'stock', 'threads': 8, 'decoder_threads': 2, 'filter_threads': 2, 'validation_threads': 4}}
    if args.mode == 'confirm':
        configurations = {'baseline-native': {'package': str(BASELINE)},
                          'baseline-stock': {'package': str(BASELINE), 'engine': 'stock'},
                          'candidate-native': {'package': str(ROOT)},
                          'candidate-stock': {'package': str(ROOT), 'engine': 'stock'}}
    directory = args.directory or WORK/(args.mode+'-'+time.strftime('%Y%m%dT%H%M%S', time.gmtime())+'-'+uuid.uuid4().hex[:8])
    check_mounts(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory/'report.json'
    package_hashes = {label: {p.name: sha256_file(p) for p in sorted((Path(c['package'])/'ffv2').glob('*.py'))}
                      for label,c in configurations.items()}
    if path.exists():
        report = json.loads(path.read_text())
        if (report['configurations'] != configurations or report['package_source_sha256'] != package_hashes or
                report['runner_sha256'] != sha256_file(Path(__file__)) or report['trials'] != args.trials or report['profiles'] != profiles):
            raise RuntimeError('Resume requires the same sources, runner, profiles and trial count')
        for row in report['cases']:
            if sha256_file(Path(row['output'])) != row['sha256']:
                raise RuntimeError('Saved completed output changed')
    else:
        sample = snapshot(directory)
        reasons = Policy().admission(sample, 3*1024**3, 8*1024**3)
        if reasons:
            raise RuntimeError(str(reasons))
        report = {'schema_version': 1, 'status': 'running', 'mode': args.mode, 'directory': str(directory),
                  'profiles': profiles, 'configurations': configurations, 'trials': args.trials, 'seconds': 60, 'start_seconds': 60,
                  'cases': [], 'summary': {}, 'cpu_samples': [], 'attempts': [], 'quality': {},
                  'runner_sha256': sha256_file(Path(__file__)), 'package_source_sha256': package_hashes,
                  'engine_selection_id': selected['selection_id'], 'resources': sample.json(),
                  'system_memory_checks_ignored': Policy().ignore_system_memory,
                  'inherited_nice': inherited_nice, 'controlled_job_nice': job_nice,
                  'estimated_peak_job_bytes': 3*1024**3, 'estimated_new_storage_bytes': 8*1024**3,
                  'quality_thresholds': {'vmaf_delta_min': -.10, 'psnr_y_delta_min': -.05, 'ssim_delta_min': -.00001, 'size_ratio_max': 1.02},
                  'scope': 'Seeded sequential real-media cases; sampled warmups excluded. Calibration chooses settings; independent confirmation is required.'}
    def save():
        write_json(path, report)
    def sample_encode(child, state, target):
        deadline = time.monotonic()+20
        while child.poll() is None and time.monotonic() < deadline:
            for live in state.glob('jobs/*/attempt-*/encode.request.live.json'):
                try:
                    value = json.loads(live.read_text())
                    info = process_info(value['pid'])
                    if value['worker_pid'] != child.pid or not info or info['exit_abstime'] or info['start_abstime'] != value['start_abstime']:
                        continue
                    command = subprocess.check_output(['/bin/ps', '-p', str(value['pid']), '-o', 'comm='], text=True, timeout=2).strip()
                    if Path(command).name != 'ffmpeg':
                        continue
                    log = target.with_suffix('.sampler.log')
                    with log.open('xb') as stream:
                        sampler = subprocess.Popen(['/usr/bin/sample', str(value['pid']), '3', '5', '-mayDie', '-file', str(target)], stdout=stream, stderr=stream)
                    return sampler, {'pid': value['pid'], 'birth': value['start_abstime'], 'worker_pid': child.pid,
                                     'path': str(target), 'log': str(log), 'warmup_excluded': True}
                except (OSError, ValueError, KeyError, subprocess.SubprocessError):
                    continue
            time.sleep(.02)
        return None, {'status': 'unavailable', 'reason': 'No live owned encoder registration before completion'}
    try:
        report['status'] = 'running'
        save()
        rng = random.Random(202611038)
        for trial in range(args.trials+1):
            pairs = [(profile,label) for profile in profiles for label in configurations]
            rng.shuffle(pairs)
            for profile,label in pairs:
                if any(row['profile']==profile and row['label']==label and row['trial']==trial for row in report['cases']):
                    continue
                config, source = configurations[label], profiles[profile]
                binary = selected['binaries'] if config.get('engine') != 'stock' else {name:'/opt/homebrew/bin/'+name for name in ('ffmpeg','ffprobe')}
                identity = profile+'-'+label+'-'+str(trial)+'-'+uuid.uuid4().hex[:8]
                spec = {'operation':'transcode','input':source['input'],'start':60,'duration':60,'output':str(directory/(identity+'.mp4')),
                        'encoder':'software','rate_control':'quality','fps':source['fps'],'max_width':source['width'],'max_height':source['height'],'timeout_seconds':1200}
                spec.update({k:config[k] for k in ('threads','decoder_threads','filter_threads','validation_threads') if k in config})
                state = directory/(label+'-state')
                request = {'package':config['package'],'ffmpeg':binary['ffmpeg'],'ffprobe':binary['ffprobe'],'state':str(state),
                           'spec':spec,'label':label,'trial':trial,'warmup':trial==0,'matched_progress':True}
                stdout, stderr = directory/(identity+'.stdout.json'),directory/(identity+'.stderr.log')
                started = time.monotonic()
                sampler, sampling = None, None
                with stdout.open('xb') as out, stderr.open('xb') as err:
                    child = subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--case',json.dumps(request)],stdout=out,stderr=err)
                    if args.mode=='calibrate' and trial==0 and label in ('native4','stock4'):
                        sampler,sampling = sample_encode(child,state,directory/(identity+'.sample.txt'))
                    child.wait(timeout=1300)
                if sampler:
                    try:
                        sampler.wait(timeout=12)
                    except subprocess.TimeoutExpired:
                        sampler.terminate();sampler.wait(timeout=5)
                    sampling['exit_code'] = sampler.returncode
                    if Path(sampling['path']).is_file():
                        sampling['sha256'] = sha256_file(Path(sampling['path']))
                if sampling:
                    report['cpu_samples'].append({'profile':profile,'label':label,**sampling})
                report['attempts'].append({'profile':profile,'label':label,'trial':trial,'exit_code':child.returncode,'stdout':str(stdout),'stderr':str(stderr)})
                save()
                if child.returncode:
                    raise RuntimeError(stderr.read_text()[-5000:])
                row = json.loads(stdout.read_text())
                row.update(profile=profile, process_wall_seconds=time.monotonic()-started)
                report['cases'].append(row)
                save()
                print(json.dumps({'profile':profile,'label':label,'trial':trial,'seconds':round(row['total_seconds'],3)}),flush=True)
        for profile in profiles:
            for label in configurations:
                rows = [row for row in report['cases'] if row['profile']==profile and row['label']==label and not row['warmup']]
                report['summary'][profile+'/'+label] = {'n':len(rows), **{key:statistics.median(row[key] for row in rows) for key in
                    ('total_seconds','encode_seconds','decode_seconds','planning_seconds','capability_seconds','bytes')},
                    'output_hashes':sorted({row['sha256'] for row in rows})}
        if {label:{p.name:sha256_file(p) for p in sorted((Path(c['package'])/'ffv2').glob('*.py'))} for label,c in configurations.items()} != package_hashes:
            raise RuntimeError('Runtime package changed during measurement')
        report['status'] = 'timing_completed'
        save()
    except BaseException as error:
        report.update(status='failed',error=str(error)[:6000]);save();raise
    print(json.dumps({'report':str(path),'summary':report['summary']}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
