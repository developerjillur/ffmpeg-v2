"""Trusted CLI consumer-এর isolated PATH; engine snapshot ও whole-tree watchdog।"""
from __future__ import annotations
import os
from pathlib import Path
import uuid

from .config import CODE_ROOT, PROJECT_MOUNT, check_mounts, within
from .engine import selection
from .errors import FFV2Error
from .io import digest, write_json
from .resources import snapshot
from .store import Store
from .worker import host_lock, supervised

def environment(settings, directory):
    selected = selection(verify_hashes=True)
    if not selected:
        raise FFV2Error('engine_not_active','Consumer environment-এর জন্য verified active engine প্রয়োজন।')
    directory.mkdir(mode=0o700)
    engine_path = directory/'engine.json'
    write_json(engine_path,selected)
    shims = directory/'bin'
    shims.mkdir(mode=0o700)
    for name in ('ffmpeg','ffprobe','ffplay'):
        if name in selected['binaries']:
            os.symlink(CODE_ROOT/'bin'/(name+'-v2'), shims/name)
    return {'PATH':str(shims)+os.pathsep+os.environ.get('PATH','/usr/bin:/bin'), 'PYTHONPATH':str(CODE_ROOT),
            'FFV2_PINNED_ENGINE':str(engine_path), 'FFV2_PROJECT_ROOT':str(__import__('ffv2.config',fromlist=['PROJECT']).PROJECT)}, selected

def run(settings, command, cwd, *, timeout=1800):
    if type(timeout) is not int or not 5 <= timeout <= 43200:
        raise FFV2Error('consumer_timeout_invalid','Consumer timeout 5–43200 seconds দিন।')
    if not command or any(not isinstance(s,str) or '\0' in s for s in command):
        raise FFV2Error('consumer_command_invalid','Trusted CLI program ও arguments দিন; shell syntax নয়।')
    cwd=Path(cwd).resolve(strict=True)
    check_mounts(cwd)
    if not cwd.is_dir() or not any(within(cwd,root.resolve()) for root in (*settings.output_roots, PROJECT_MOUNT)):
        raise FFV2Error('consumer_directory_denied','Consumer work directory project/NexaWork-এর মধ্যে হতে হবে।')
    store=Store(settings)
    directory=store.root/('consumer-'+uuid.uuid4().hex)
    env,selected=environment(settings,directory)
    plan={'schema_version':1,'kind':'consumer','spec':{'operation':'consumer','output':str(directory/'result.json')},
          'engine_selection_id':selected['selection_id'],'argv':command,'estimates':{'job_memory_bytes':2*1024**3,'output_budget_bytes':4*1024**3},'timeout_seconds':timeout}
    plan['plan_id']=digest(plan)
    queued=store.enqueue(plan)
    job=store.claim(queued['id'])
    attempt=store.root/'jobs'/job['id']/('attempt-%03d'%job['attempt'])
    attempt.mkdir(parents=True)
    write_json(attempt/'plan.json',plan)
    try:
        with host_lock(settings) as lock_fd:
            receipt=supervised(command,'consumer',job,attempt,settings,snapshot(cwd),lock_fd,cwd,
                               cwd=cwd,process_kind='tool',environment=env)
        result={'status':'completed','job_id':job['id'],'selection_id':selected['selection_id'],'receipt':receipt,'environment_directory':str(directory),
                'stdout_tail':receipt.get('stdout_tail','')}
        write_json(directory/'result.json',result)
        store.update(job['id'],'completed',receipt=result)
        return result
    except BaseException as error:
        store.update(job['id'],'failed',error=error.payload() if isinstance(error,FFV2Error) else {'code':'consumer_failed','message':str(error)[:1000]})
        raise
