#!/usr/bin/python3 -B
"""Actual RC install→version-only update→rollback→checkpoint recovery→final selection।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.io import sha256_file, write_json
from ffv2.releases import ACTIVE, package_files


class Client:
    def __init__(self, launcher, state, log):
        self.log = log.open('xb')
        self.child = subprocess.Popen([str(launcher), '--state-dir', str(state), '--input-root', str(lab_path('')), 'mcp'],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log, bufsize=0)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.child.stdout, selectors.EVENT_READ)
        self.buffer, self.identity = bytearray(), 0
        self.request('initialize', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'release-check', 'version': '1'}})
        self.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})

    def send(self, value):
        self.child.stdin.write((json.dumps(value)+'\n').encode())
        self.child.stdin.flush()

    def request(self, method, params):
        self.identity += 1
        self.send({'jsonrpc': '2.0', 'id': self.identity, 'method': method, 'params': params})
        deadline = time.monotonic()+45
        while b'\n' not in self.buffer:
            if not self.selector.select(max(0, deadline-time.monotonic())):
                raise RuntimeError('Installed MCP response timeout')
            data = os.read(self.child.stdout.fileno(), 65536)
            if not data or len(self.buffer)+len(data) > 1024**2:
                raise RuntimeError('Installed MCP closed or exceeded response budget')
            self.buffer.extend(data)
        line, _, rest = self.buffer.partition(b'\n')
        self.buffer = bytearray(rest)
        response = json.loads(line)
        if response.get('id') != self.identity or response.get('error'):
            raise RuntimeError('Installed MCP protocol mismatch')
        return response['result']

    def call(self, name, arguments, error=None):
        value = self.request('tools/call', {'name': name, 'arguments': arguments})
        if error:
            parsed = json.loads(value['content'][0]['text'])
            if not value.get('isError') or parsed.get('code') != error:
                raise RuntimeError('Expected MCP refusal '+error+': '+str(value)[:1500])
            return parsed
        if value.get('isError'):
            raise RuntimeError('Installed MCP tool failed: '+str(value)[:1500])
        return value['structuredContent']

    def close(self):
        self.child.stdin.close()
        try:
            self.child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.child.terminate()
            self.child.wait(timeout=5)
        self.child.stdout.close()
        self.selector.close()
        self.log.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--acceptance', required=True, type=Path)
    parser.add_argument('--rc-version', default='0.5.0rc1')
    parser.add_argument('--final-version', default='0.5.0')
    parser.add_argument('--work-root', type=Path, default=Path(str(lab_path('ffmpeg-v2-phase7'))))
    args = parser.parse_args()
    if args.rc_version != args.final_version+'rc1':
        raise RuntimeError('An explicit rc1 to final version-only transition is required')
    directory = args.work_root/('lifecycle-'+time.strftime('%Y%m%dT%H%M%S', time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    state, launcher = directory/'state', ROOT/'bin/ffv2-release'
    source = Path(str(lab_path('ffmpeg-v2-phase6/quick-20261103T094955-1bccf5b0/real-cfr.mkv')))
    report = {'schema_version': 1, 'status': 'running', 'tests': {}, 'directory': str(directory), 'source': str(source), 'source_sha256': sha256_file(source)}
    serial = 0
    old, source_client, child = None, None, None

    def save():
        write_json(directory/'report.json', report)

    def passed(name, **details):
        report['tests'][name] = {'status': 'pass', **details}
        save()
        print(json.dumps({'check': name, 'status': 'pass'}), flush=True)

    def cli(arguments, *, program=launcher, expected=None, timeout=120):
        nonlocal serial
        serial += 1
        result = subprocess.run([str(program), '--state-dir', str(state), *arguments], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        write_json(directory/('cli-%03d.json'%serial), {'argv': [str(program), *arguments], 'exit_code': result.returncode, 'stdout': result.stdout[-200000:], 'stderr': result.stderr[-12000:]})
        if expected:
            value = json.loads(result.stderr)
            if result.returncode == 0 or value.get('error', {}).get('code') not in expected:
                raise RuntimeError('Unexpected CLI refusal: '+result.stderr[-2000:])
            return value['error']
        if result.returncode:
            raise RuntimeError('Installed CLI failed: '+result.stderr[-4000:])
        return json.loads(result.stdout)

    try:
        previous_stable = json.loads(ACTIVE.read_text()) if ACTIVE.exists() else None
        report['previous_stable'] = previous_stable
        before = package_files()
        acceptance = json.loads(args.acceptance.read_text())
        if acceptance['package_files'] != before or (ROOT/'ffv2/__init__.py').read_text().count(args.rc_version) != 1:
            raise RuntimeError('Measured release candidate source required')
        installed = cli(['release', 'install', '--source', str(ROOT), '--acceptance', str(args.acceptance.resolve())], program=ROOT/'bin/ffv2')
        rc = installed['active']
        if subprocess.check_output([str(launcher), '--version'], text=True).strip() != args.rc_version:
            raise RuntimeError('Frozen RC launch version mismatch')
        doctor = cli(['doctor'])
        report.update(rc=rc, engine_selection_id=doctor['capabilities']['engine_selection_id'] if 'engine_selection_id' in doctor['capabilities'] else rc['engine_selection_id'])
        passed('frozen_rc_install', release_id=rc['release_id'])
        old = Client(launcher, state, directory/'retained-rc-mcp.log')
        source_client = Client(ROOT/'bin/ffv2', state, directory/'retained-source-mcp.log')
        old.call('ffv2_doctor', {})
        queued_spec = {'operation': 'frame', 'input': str(source), 'output': str(directory/'queued-frame.jpg')}
        queued = old.call('ffv2_submit', {'spec': queued_spec})
        pointer = sha256_file(ACTIVE)
        error = cli(['release', 'activate', '--manifest', rc['manifest']], expected=('release_jobs_active',))
        if sha256_file(ACTIVE) != pointer:
            raise RuntimeError('Blocked update changed active selection')
        old.call('ffv2_job_cancel', {'job_id': queued['id']})
        passed('queued_update_fence', code=error['code'], selection_unchanged=True)
        invalid = {**acceptance, 'package_files': {**acceptance['package_files'], 'ffv2/__init__.py': '0'*64}}
        bad_path = directory/'tampered-acceptance.json'
        write_json(bad_path, invalid)
        error = cli(['release', 'install', '--source', str(ROOT), '--acceptance', str(bad_path)], expected=('release_unverified',))
        if sha256_file(ACTIVE) != pointer:
            raise RuntimeError('Rejected install changed selection')
        passed('tampered_candidate_refusal', code=error['code'])
        spec = {'operation': 'transcode', 'input': str(source), 'output': str(directory/'recovered.mp4'), 'encoder': 'software', 'fps': 30,
                'duration': 120, 'checkpoint_seconds': 10, 'threads': 1, 'timeout_seconds': 600}
        checkpoint_job = old.call('ffv2_submit', {'spec': spec})
        cp_path = state/'jobs'/checkpoint_job['id']/'checkpoints/manifest.json'
        log_path = directory/'rc-worker.log'
        with log_path.open('xb') as log:
            child = subprocess.Popen([str(launcher), '--ignore-system-memory', '--state-dir', str(state), 'worker', '--job-id', checkpoint_job['id']], stdout=log, stderr=log)
        deadline = time.monotonic()+180
        saved = None
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError('RC checkpoint worker exited before cancellation: '+log_path.read_text()[-3000:])
            if cp_path.exists():
                checkpoint = json.loads(cp_path.read_text())
                if len(checkpoint['segments']) >= 2:
                    saved = checkpoint
                    break
            time.sleep(.03)
        if not saved:
            raise RuntimeError('No durable checkpoint appeared before timeout')
        error = cli(['release', 'activate', '--manifest', rc['manifest']], expected=('worker_busy', 'release_jobs_active'))
        if sha256_file(ACTIVE) != pointer:
            raise RuntimeError('Running update changed active selection')
        old.call('ffv2_job_cancel', {'job_id': checkpoint_job['id']})
        child.wait(timeout=20)
        stopped = cli(['status', checkpoint_job['id']])
        if stopped['status'] != 'cancelled' or Path(spec['output']).exists():
            raise RuntimeError('Checkpoint cancellation publication/state mismatch')
        passed('running_update_fence_and_checkpoint_cancel', code=error['code'], segments=len(saved['segments']), published=False)
        affected = [ROOT/'ffv2/__init__.py', ROOT/'pyproject.toml']
        print(json.dumps({'affected_version_files': [str(p) for p in affected], 'from': args.rc_version, 'to': args.final_version}), flush=True)
        for path in affected:
            original = path.read_text()
            if original.count(args.rc_version) != 1:
                raise RuntimeError('Only the declared version literal may change')
            copy = directory/('before-'+path.name)
            copy.write_text(original)
            path.write_text(original.replace(args.rc_version, args.final_version))
        after = package_files()
        changed = sorted(key for key in before if before[key] != after[key])
        if changed != ['ffv2/__init__.py', 'pyproject.toml']:
            raise RuntimeError('Version-only release bridge includes functional changes')
        regression = subprocess.run([sys.executable, '-B', str(ROOT/'scripts/verify_unit_matrix.py'), '--work-root', str(args.work_root)], cwd=ROOT, capture_output=True, text=True, timeout=120)
        if regression.returncode:
            raise RuntimeError('Final version regression failed: '+regression.stderr[-3000:])
        unit_path = Path(json.loads(regression.stdout)['report'])
        final_acceptance = {**acceptance, 'package_files': after, 'gates': {**acceptance['gates'],
            'unit_tests': {'status': 'pass', 'path': str(unit_path), 'sha256': sha256_file(unit_path)}},
            'version_transition': {'from': args.rc_version, 'to': args.final_version, 'changed_files': changed, 'functional_files_identical': True,
                'measured_acceptance': str(args.acceptance.resolve()), 'measured_acceptance_sha256': sha256_file(args.acceptance),
                'before_package_files': before, 'scope': 'Only package version literals changed; timing was measured on RC bytes. Functional implementation, argv and native closure are identical.'}}
        final_path = directory/'final-version-acceptance.json'
        write_json(final_path, final_acceptance)
        report['final_acceptance'] = str(final_path)
        final = cli(['release', 'install', '--source', str(ROOT), '--acceptance', str(final_path)])['active']
        if subprocess.check_output([str(launcher), '--version'], text=True).strip() != args.final_version:
            raise RuntimeError('Final frozen version mismatch')
        report['final'] = final
        error = old.call('ffv2_submit', {'spec': queued_spec}, error='release_changed')
        prior = old.call('ffv2_job_status', {'job_id': checkpoint_job['id']})
        if prior['status'] != 'cancelled':
            raise RuntimeError('Old MCP read changed prior job')
        passed('version_only_update_and_stale_mcp_refusal', changed_files=changed, code=error['code'], retained_status=prior['status'], unit_report=str(unit_path))
        error = source_client.call('ffv2_submit', {'spec': queued_spec}, error='runtime_code_changed')
        passed('mutable_source_mcp_edit_refusal', code=error['code'], scope='Existing source process refused after actual version-file edit; no job queued')
        error = cli(['retry', checkpoint_job['id']], expected=('runtime_code_changed',))
        passed('cross_release_checkpoint_refusal', code=error['code'])
        reverted = cli(['release', 'rollback'])['active']
        if reverted['release_id'] != rc['release_id']:
            raise RuntimeError('Rollback did not restore the measured RC pair')
        cli(['retry', checkpoint_job['id']])
        cli(['--ignore-system-memory', 'worker', '--job-id', checkpoint_job['id']], timeout=660)
        result = cli(['status', checkpoint_job['id']])
        reused = result['receipt']['checkpoints']['reused_segments']
        if result['status'] != 'completed' or not set(map(int, saved['segments'])) <= set(reused):
            raise RuntimeError('Rollback failed to reuse previously validated segments')
        if int(result['receipt']['validation']['full_decode']['last_progress']['frame']) != 3600:
            raise RuntimeError('Rollback recovered output frame count mismatch')
        for row in saved['segments'].values():
            if sha256_file(Path(row['path'])) != row['sha256']:
                raise RuntimeError('Retained successful checkpoint changed')
        passed('rollback_and_real_checkpoint_recovery', release_id=reverted['release_id'], frames=3600,
               reused_segments=reused, output_sha256=result['receipt']['output_sha256'], receipt=result['receipt']['directory'])
        if previous_stable and previous_stable['version'] not in (args.rc_version, args.final_version):
            cli(['release', 'activate', '--manifest', previous_stable['manifest']])
            if subprocess.check_output([str(launcher), '--version'], text=True).strip() != previous_stable['version']:
                raise RuntimeError('Prior stable release was not retained and runnable')
            passed('previous_stable_retained_and_runnable', release_id=previous_stable['release_id'], version=previous_stable['version'])
        cli(['release', 'activate', '--manifest', final['manifest']])
        linked = cli(['release', 'link-launchers'])
        if subprocess.check_output([str(Path.home()/'.local/bin/ffv2'), '--version'], text=True).strip() != args.final_version:
            raise RuntimeError('User-local launcher does not load final release')
        report['doctor'] = cli(['doctor'])
        passed('final_reactivation_and_user_launchers', release_id=final['release_id'], launchers=linked['launchers'])
        report['status'] = 'completed'
    except BaseException as error:
        report.update(status='failed', error=str(error)[:6000])
        raise
    finally:
        if old:
            old.close()
        if source_client:
            source_client.close()
        if child and child.poll() is None:
            child.terminate()
            child.wait(timeout=20)
        save()
    print(json.dumps({'report': str(directory/'report.json'), 'tests': len(report['tests']), 'final_acceptance': report['final_acceptance']}))


if __name__ == '__main__':
    main()
