"""Media exec-এর আগে birth-bound registration ও স্বাধীন crash watchdog।"""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from .darwin import process_info
from .io import write_json

def alive(pid, birth):
    value = process_info(pid)
    return bool(value and not value['exit_abstime'] and value['start_abstime'] == birth)

def watch(path):
    request = json.loads(path.read_text())
    record_path = Path(request['live_process']['path'])
    value = json.loads(record_path.read_text())
    if value['nonce'] != request['live_process']['nonce']:
        raise RuntimeError('Guardian registration nonce mismatch')
    ready = record_path.with_suffix('.guardian-ready.json')
    write_json(ready, {'nonce': value['nonce'], 'guardian_pid': os.getpid()})
    reason = 'process_exited'
    while alive(value['pid'], value['start_abstime']):
        if not alive(request['owner_pid'], request['owner_birth']) or not alive(request['supervisor_pid'], request['supervisor_birth']):
            reason = 'owner_or_supervisor_lost'
            try:
                if os.getpgid(value['pid']) != value['pid']:
                    reason = 'process_group_changed'
                    break
                os.killpg(value['pid'], signal.SIGTERM)
                deadline = time.monotonic() + 2
                while alive(value['pid'], value['start_abstime']) and time.monotonic() < deadline:
                    time.sleep(.02)
                if alive(value['pid'], value['start_abstime']) and os.getpgid(value['pid']) == value['pid']:
                    os.killpg(value['pid'], signal.SIGKILL)
            except ProcessLookupError:
                pass
            break
        time.sleep(.02)
    write_json(record_path.with_suffix('.guardian-receipt.json'), {'nonce': value['nonce'], 'reason': reason,
               'pid': value['pid'], 'start_abstime': value['start_abstime'], 'finished_at': time.time()})

def launch(path):
    request = json.loads(path.read_text())
    if os.getppid() != request['supervisor_pid'] or not alive(request['owner_pid'], request['owner_birth']) or not alive(request['supervisor_pid'], request['supervisor_birth']):
        raise RuntimeError('Owner/supervisor disappeared before media launch')
    info = process_info(os.getpid())
    if not info or os.getpgrp() != os.getpid():
        raise RuntimeError('Media process identity unavailable')
    record_path = Path(request['live_process']['path'])
    write_json(record_path, {'nonce': request['live_process']['nonce'], 'worker_pid': request['owner_pid'],
        'supervisor_pid': request['supervisor_pid'], 'pid': os.getpid(), 'start_abstime': info['start_abstime']})
    with record_path.with_suffix('.guardian.log').open('xb') as log:
        guardian = subprocess.Popen([sys.executable, '-B', '-m', 'ffv2.guardian', 'watch', str(path)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True, pass_fds=(request['host_lock_fd'],))
    deadline = time.monotonic() + 10
    ready = record_path.with_suffix('.guardian-ready.json')
    while not ready.is_file():
        if guardian.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError('Guardian startup failed; media was not executed')
        time.sleep(.01)
    if json.loads(ready.read_text()).get('nonce') != request['live_process']['nonce']:
        raise RuntimeError('Guardian acknowledgement mismatch')
    os.execvpe(request['argv'][0], request['argv'], os.environ)

def main():
    mode, raw = sys.argv[1:]
    (watch if mode == 'watch' else launch)(Path(raw))

if __name__ == '__main__':
    main()
