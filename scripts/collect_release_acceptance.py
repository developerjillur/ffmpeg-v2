#!/usr/bin/python3 -B
"""Measured gates ও current package/engine-কে pre-install acceptance-এ বাঁধে।"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import PROJECT
from ffv2.engine import selection
from ffv2.io import sha256_file, write_json
from ffv2.releases import REQUIRED, package_files


def performance_check(report,files,active):
    if report.get('phase')==11:
        from performance_phase11 import validate
        return validate(report,files,active)
    raw=Path(report['source_report'])
    if sha256_file(raw)!=report['source_sha256']:raise RuntimeError('Performance source report changed')
    timing=json.loads(raw.read_text())
    source={Path(key).name:checksum for key,checksum in files.items() if key.startswith('ffv2/')}
    if timing['package_source_sha256']['candidate-native']!=source:raise RuntimeError('Performance measured a different SDK source')
    if report.get('phase')==8:
        expected={'bbb-1080','tos-liveaction'};quality_path=Path(report['quality_report'])
        if (report.get('mode')!='confirm' or not report.get('release_performance_accepted') or set(timing['profiles'])!=expected or
                timing['trials']<9 or sha256_file(quality_path)!=report['quality_sha256']):
            raise RuntimeError('Independent nine-pair Phase 8 timing and full-frame quality required')
        quality=json.loads(quality_path.read_text())
        if quality['status']!='completed' or quality['source_sha256']!=report['source_sha256']:raise RuntimeError('Phase 8 quality must bind the same immutable timing')
        promoted=[report['comparisons'][profile+'/'+key] for profile in expected for key in ('candidate-native','vs_previous_stock')]
        if any(not row['promotion_allowed'] or row['n_pairs']!=timing['trials'] for row in promoted):raise RuntimeError('Both target pipelines must beat the previous native and Stock presets')
        if timing['package_source_sha256']['candidate-stock']!=source:raise RuntimeError('Matched Stock control measured a different SDK source')
    else:
        promoted=[row for key,row in report['comparisons'].items() if key.endswith('/candidate-native')]
        if len(promoted)!=4 or any(not row['promotion_allowed'] for row in promoted):raise RuntimeError('All four real-media workflow speed/quality gates must pass')


def main():
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    parser = argparse.ArgumentParser()
    for name in REQUIRED:
        parser.add_argument('--' + name.replace('_', '-'), required=True, type=Path)
    parser.add_argument('--extra', action='append', default=[], type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('Acceptance already exists; retain original evidence')
    files = package_files()
    active = selection(verify_hashes=True)
    value = {'schema_version': 1, 'status': 'running', 'maintainer': 'Jillur Rahman',
             'package_files': files, 'engine_manifest': str(PROJECT/'.runtime/active-engine.json'),
             'engine_selection_id': active['selection_id'], 'gates': {}, 'supplements': [],
             'created_at': time.time(), 'scope': 'Bounded local release acceptance; historical native/soak gates and fresh wrapper checks are identified by their original receipts.'}
    for name in REQUIRED:
        path = getattr(args, name).resolve(strict=True)
        report = json.loads(path.read_text())
        if report.get('status') != 'completed':
            raise RuntimeError(name + ': completed report required')
        tests = report.get('tests', {})
        if tests and any(row.get('status') != 'pass' for row in tests.values()):
            raise RuntimeError(name + ': non-passing test record')
        if name == 'unit_tests' and (report['package_files'] != files or len(report['runs']) != 2 or any(row['tests'] < 126 or row['exit_code'] for row in report['runs'])):
            raise RuntimeError('Fresh two-runtime regression required for these package bytes')
        if name == 'performance':
            performance_check(report,files,active)
            if report.get('phase')==11:
                unit=json.loads(Path(args.unit_tests).read_text())
                if any(run['tests']<176 for run in unit['runs']):raise RuntimeError('Fresh Phase 11 promotion-control regression required')
        prefix = report.get('install_prefix')
        if prefix and Path(prefix).resolve() != Path(active['install_prefix']).resolve():
            raise RuntimeError(name + ': different native candidate')
        value['gates'][name] = {'status': 'pass', 'path': str(path), 'sha256': sha256_file(path),
                                'test_count': len(tests) if tests else None}
    for path in args.extra:
        path = path.resolve(strict=True)
        report = json.loads(path.read_text())
        if report.get('status') != 'completed':
            raise RuntimeError('Completed supplement required: ' + str(path))
        value['supplements'].append({'path': str(path), 'sha256': sha256_file(path)})
    if package_files() != files:
        raise RuntimeError('Package changed during evidence collection')
    value['status'] = 'completed'
    write_json(args.output, value)
    print(json.dumps({'acceptance': str(args.output), 'gates': len(value['gates']), 'files': len(files)}))


if __name__ == '__main__':
    main()
