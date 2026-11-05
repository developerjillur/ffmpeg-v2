#!/usr/bin/python3 -B
"""Default CLI-তে পরীক্ষিত pool ও byte-identical output যাচাই।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(str(lab_path('ffmpeg-v2-phase4')))
sys.path.insert(0, str(ROOT))
from ffv2.config import check_mounts
from ffv2.io import sha256_file, write_json

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--benchmark', type=Path)
    parser.add_argument('--launcher', type=Path)
    args = parser.parse_args()
    reports = [args.benchmark] if args.benchmark else [WORK / 'balanced-20261103T084556-25ed478b/report.json',
               WORK / 'balanced-20261103T091601-c5d721a8/report.json']
    measured = [json.loads(p.read_text()) for p in reports]
    if any(r['status'] != 'completed' for r in measured):
        raise RuntimeError('Completed timing/quality reports required')
    directory = WORK / ('default-cli-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    check_mounts(directory)
    directory.mkdir()
    report = {'status': 'running', 'directory': str(directory), 'checks': {},
              'launcher': str(args.launcher or ROOT/'bin/ffv2'),
              'script_sha256': sha256_file(Path(__file__)),
              'measured_reports': {str(p): sha256_file(p) for p in reports},
              'contract': 'No explicit thread pools; actual CLI; identical encoded file SHA-256 to quality-approved measured case.'}
    try:
        for name, profile in measured[0]['profiles'].items():
            reference = measured[1] if name == 'bbb-2160-to1080' and not args.benchmark else measured[0]
            label = 'candidate-native' if args.benchmark else 'balanced'
            row = next(r for r in reference['cases'] if r['profile'] == name and r['label'] == label and not r['warmup'])
            spec = {'operation': 'transcode', 'input': profile['input'], 'output': str(directory / (name + '.mp4')),
                    'encoder': 'software', 'rate_control': 'quality', 'fps': profile.get('fps', 30),
                    'start': 60, 'duration': 60, 'max_width': profile['width'], 'max_height': profile['height'],
                    'timeout_seconds': 1200}
            spec_path = directory / (name + '.spec.json')
            write_json(spec_path, spec)
            base = [str(args.launcher)] if args.launcher else [sys.executable, '-B', str(ROOT/'bin/ffv2')]
            base += ['--ignore-system-memory', '--state-dir', str(directory/'state')]
            started = time.monotonic()
            child = subprocess.run([*base, 'run', str(spec_path)], capture_output=True, text=True, timeout=1300)
            if child.returncode:
                raise RuntimeError((child.stderr or child.stdout)[-2500:])
            value = json.loads(child.stdout)
            if value['status'] != 'completed':
                raise RuntimeError(str(value.get('error')))
            receipt = value['receipt']
            plan = json.loads((Path(receipt['directory']) / 'plan.json').read_text())
            tuning = plan['runtime_tuning']
            expected_filter = 4 if name == 'bbb-2160-to1080' else 2
            if (tuning['encoder_threads'], tuning['decoder_threads'], tuning['filter_threads'], tuning['validation_threads']) != (4, 2, expected_filter, 4):
                raise RuntimeError('Default pool mismatch: ' + str(tuning))
            if receipt['output_sha256'] != row['sha256']:
                raise RuntimeError('Default output differs from measured quality-approved case: ' + name)
            report['checks'][name] = {'passed': True, 'runtime_tuning': tuning, 'output_sha256': receipt['output_sha256'],
                'runtime_code_id':plan.get('runtime_code_id'), 'engine_selection_id':plan['binary'].get('engine_selection_id'),
                'reference_sha256': row['sha256'], 'receipt': str(Path(receipt['directory']) / 'receipt.json'),
                'wall_seconds': time.monotonic() - started, 'output': value['output']}
            write_json(directory / 'report.json', report)
            print(json.dumps({'profile': name, 'passed': True}), flush=True)
        report['status'] = 'completed'
    except BaseException as error:
        report.update(status='failed', error=str(error)[:3000])
        raise
    finally:
        write_json(directory / 'report.json', report)
    print(json.dumps({'report': str(directory / 'report.json'), 'checks': len(report['checks'])}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
