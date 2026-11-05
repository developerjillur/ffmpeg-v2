"""Immutable code/engine pair, quiescent activation ও retained rollback।"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid
from contextlib import closing, contextmanager
import fcntl

from .config import CODE_ROOT, PROJECT, check_mounts
from .engine import selection
from .errors import FFV2Error
from .io import digest, rename_directory_new, sha256_file, write_json
from .store import Store
from .worker import host_lock
from .checkpoints import sync_directory

ROOT = PROJECT / '.runtime/releases'
ACTIVE = PROJECT / '.runtime/active-release.json'
REQUIRED = ('unit_tests', 'native_media', 'extended_media', 'performance', 'phase5', 'checkpoint', 'soak', 'formats', 'external_fate', 'consumer')

@contextmanager
def lifecycle_lock(settings, *, exclusive=False):
    path=settings.host_lock.with_name(settings.host_lock.name+'.release')
    check_mounts(path)
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    descriptor=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        yield
    finally:
        os.close(descriptor)

def assert_current():
    expected=os.environ.get('FFV2_RELEASE_ID')
    if expected and (not ACTIVE.is_file() or read(ACTIVE).get('release_id')!=expected):
        raise FFV2Error('release_changed','Installed release বদলেছে; এই CLI/MCP connection নতুন করে শুরু করুন।',retryable=True,exit_code=75)

def package_files(root=CODE_ROOT):
    paths = [*sorted((root/'ffv2').glob('*.py')),
             *(root/'bin'/name for name in ('ffv2','ffmpeg-v2','ffprobe-v2','ffplay-v2','ffv2-release')),
             root/'LICENSE', root/'pyproject.toml', root/'upstream.lock.json', *sorted((root/'third_party').rglob('COPYING'))]
    if not 10 <= len(paths) <= 128 or any(p.is_symlink() or not p.is_file() or p.stat().st_size > 2*1024**2 for p in paths):
        raise FFV2Error('release_files_invalid', 'Release allowlist-এর regular bounded files প্রয়োজন।')
    return {str(p.relative_to(root)): sha256_file(p) for p in paths}

def read(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2*1024**2:
        raise FFV2Error('release_manifest_invalid', 'Bounded regular release manifest প্রয়োজন।')
    return json.loads(path.read_text())

def verified(path):
    path = Path(path).resolve(strict=True)
    if path.parent.parent != ROOT.resolve() or path.name != 'release.json':
        raise FFV2Error('release_path_denied', 'Private releases directory-এর manifest প্রয়োজন।')
    value = read(path)
    if digest({k:v for k,v in value.items() if k!='manifest_id'}) != value.get('manifest_id'):
        raise FFV2Error('release_manifest_changed', 'Release manifest digest মেলেনি।')
    directory = path.parent
    if package_files(directory) != value['package_files'] or sha256_file(directory/'engine.json') != value['engine_sha256']:
        raise FFV2Error('release_changed', 'Frozen release code/engine বদলেছে; activation হয়নি।')
    selected = selection(path=directory/'engine.json', verify_hashes=True)
    if selected['selection_id'] != value['engine_selection_id']:
        raise FFV2Error('release_engine_changed', 'Frozen engine identity মেলেনি।')
    return value

def quiescent(settings):
    store = Store(settings)
    paths = {store.path, PROJECT/'.runtime/jobs.sqlite3'}
    import sqlite3
    for path in paths:
        if not path.exists():
            continue
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            active = db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','waiting_resources','running','validating')").fetchone()[0]
        if active:
            raise FFV2Error('release_jobs_active', 'Queued/running job শেষ বা explicit cancel হওয়ার পরে release বদলান।', details={'state':str(path),'active_jobs':active}, retryable=True)

def status():
    current = read(ACTIVE) if ACTIVE.exists() else None
    versions = []
    if ROOT.exists():
        for path in sorted(ROOT.glob('*/release.json'))[:64]:
            value = read(path)
            versions.append({k:value[k] for k in ('version','release_id','engine_selection_id')})
    return {'current':current,'releases':versions,'state':str(PROJECT/'.runtime'), 'policy':'quiescent update; one atomic code/engine pair pointer; previous release retained'}

def activate_manifest(path, settings, *, rollback=False, expected_release=None):
    value = verified(path)
    with host_lock(settings), lifecycle_lock(settings,exclusive=True):
        if expected_release and (not ACTIVE.is_file() or read(ACTIVE).get('release_id')!=expected_release):
            raise FFV2Error('release_changed','Rollback প্রস্তুতির পরে active release বদলেছে; বর্তমান selection inspect করুন।',retryable=True,exit_code=75)
        quiescent(settings)
        previous = None
        if ACTIVE.exists():
            previous = ACTIVE.with_name('active-release-'+uuid.uuid4().hex+'.previous.json')
            os.link(ACTIVE, previous, follow_symlinks=False)
        pointer = {'schema_version':1,'manifest':str(path),'manifest_sha256':sha256_file(path),
                   'release_id':value['release_id'],'version':value['version'],'engine_selection_id':value['engine_selection_id'],
                   'previous':str(previous) if previous else None,'activated_at':time.time(),'rollback':rollback}
        write_json(ACTIVE,pointer)
        sync_directory(ACTIVE.parent)
    return {'status':'activated','active':pointer}

def install(acceptance_path, settings, *, source=None):
    source = Path(source or CODE_ROOT).resolve(strict=True)
    acceptance_path = Path(acceptance_path).resolve(strict=True)
    acceptance = read(acceptance_path)
    selected = selection(path=Path(acceptance['engine_manifest']), verify_hashes=True)
    if not selected:
        raise FFV2Error('release_engine_required','Accepted native engine প্রয়োজন।')
    files = package_files(source)
    version_match = re.search(r'^__version__ = "([A-Za-z0-9.+_-]+)"$', (source/'ffv2/__init__.py').read_text(), re.M)
    if not version_match:
        raise FFV2Error('release_version_invalid','Source version literal পাওয়া যায়নি।')
    version = version_match.group(1)
    if (acceptance.get('status')!='completed' or acceptance.get('package_files')!=files or
        acceptance.get('engine_selection_id')!=selected['selection_id'] or
        any(acceptance.get('gates',{}).get(name,{}).get('status')!='pass' for name in REQUIRED)):
        raise FFV2Error('release_unverified','একই code/engine-এর completed pre-install acceptance প্রয়োজন।')
    for gate in REQUIRED:
        record = acceptance['gates'][gate]
        evidence = Path(record['path'])
        if sha256_file(evidence)!=record['sha256']:
            raise FFV2Error('release_evidence_changed','Acceptance evidence বদলেছে।',details={'gate':gate})
    release_id = version+'-'+digest({'files':files,'engine':selected['selection_id']})[:16]
    if not re.fullmatch(r'[A-Za-z0-9.+_-]{1,96}',release_id):
        raise FFV2Error('release_version_invalid','Version directory name গ্রহণযোগ্য নয়।')
    check_mounts(ROOT)
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    destination = ROOT/release_id
    print(json.dumps({'affected_paths':[str(destination),str(ACTIVE)],'file_count':len(files)},ensure_ascii=False),file=__import__('sys').stderr,flush=True)
    with host_lock(settings):
        quiescent(settings)
        if not destination.exists():
            stage = ROOT/('.staging-'+uuid.uuid4().hex)
            stage.mkdir(mode=0o700)
            for relative,checksum in files.items():
                target = stage/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                with (source/relative).open('rb') as incoming,target.open('xb') as output:
                    shutil.copyfileobj(incoming,output,length=1024**2)
                    output.flush()
                    os.fsync(output.fileno())
                if sha256_file(target)!=checksum:
                    raise FFV2Error('release_copy_changed','Source/copy checksum মেলেনি; staging রাখা হয়েছে।')
                target.chmod(0o500 if relative.startswith('bin/') else 0o400)
            if package_files(source)!=files:
                raise FFV2Error('release_source_changed','Copy চলাকালে source বদলেছে।')
            write_json(stage/'engine.json',selected)
            value={'schema_version':1,'maintainer':'Jillur Rahman','version':version,'release_id':release_id,
                   'package_files':files,'engine_selection_id':selected['selection_id'],'engine_sha256':sha256_file(stage/'engine.json'),
                   'acceptance':str(acceptance_path),'acceptance_sha256':sha256_file(acceptance_path),'created_at':time.time()}
            value['manifest_id']=digest(value)
            write_json(stage/'release.json',value)
            rename_directory_new(stage,destination)
            sync_directory(ROOT)
        verified(destination/'release.json')
    return activate_manifest(destination/'release.json',settings)

def rollback(settings):
    if not ACTIVE.exists():
        raise FFV2Error('release_not_installed','Active release নেই।')
    current=read(ACTIVE)
    if not current.get('previous'):
        raise FFV2Error('release_no_previous','Retained previous release নেই।')
    previous=read(Path(current['previous']))
    previous_manifest=Path(previous['manifest'])
    if sha256_file(previous_manifest)!=previous['manifest_sha256']:
        raise FFV2Error('release_previous_changed','Retained rollback manifest-এর checksum বদলেছে।')
    return activate_manifest(previous_manifest,settings,rollback=True,expected_release=current['release_id'])

def link_launchers():
    import sys
    verified(Path(read(ACTIVE)['manifest']))
    launch = PROJECT/'bin/ffv2-release'
    if not launch.is_file() or launch.is_symlink():
        raise FFV2Error('release_launcher_missing','Stable release launcher পাওয়া যায়নি।')
    destination = Path.home()/'.local/bin'
    plans = []
    for name in ('ffv2','ffmpeg-v2','ffprobe-v2','ffplay-v2'):
        path = destination/name
        if os.path.lexists(path) and (not path.is_symlink() or path.resolve() not in (PROJECT/'bin'/name,launch)):
            raise FFV2Error('release_launcher_conflict','Existing unrelated launcher রাখা হয়েছে।',details={'path':str(path)})
        plans.append({'target':str(path),'source':str(launch),'previous':os.readlink(path) if path.is_symlink() else None})
    print(json.dumps({'affected_launchers':plans},ensure_ascii=False),file=sys.stderr,flush=True)
    launch.chmod(0o755)
    destination.mkdir(parents=True,exist_ok=True)
    for plan in plans:
        path = Path(plan['target'])
        if path.is_symlink() and path.resolve()==launch:
            continue
        if plan['previous']:
            os.symlink(plan['previous'],path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.previous'))
        temporary = path.with_name('.'+path.name+'-'+uuid.uuid4().hex+'.pending')
        os.symlink(launch,temporary)
        os.replace(temporary,path)
    sync_directory(destination)
    return {'status':'installed','launchers':plans}
