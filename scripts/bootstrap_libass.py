#!/usr/bin/python3 -B
"""Verified libass source থেকে private static build; system packages বদলায় না।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import Settings, check_mounts
from ffv2.io import digest, rename_directory_new, sha256_file, write_json
from ffv2.resources import snapshot
from ffv2.store import Store
from ffv2.worker import host_lock, supervised

VERSION = '0.17.5'
SHA = 'caab4b993dd7be6187c55623b789ed75dddefea6e65938af134637c732fe094a'
URL = 'https://github.com/libass/libass/releases/download/0.17.5/libass-0.17.5.tar.gz'
AREA = Path(str(lab_path('ffmpeg-v2-core/tools/libass-bootstrap-0.17.5')))
PREFIX = AREA.parent / 'libass-0.17.5'
PKG = AREA.parent / 'pkgconf-3.0.10/bin/pkgconf'

def run(argv, **kwargs):
    subprocess.run([str(a) for a in argv], check=True, timeout=240, **kwargs)

def build():
    archive = AREA / 'libass-0.17.5.tar.gz'
    if not archive.exists():
        pending = archive.with_suffix('.part')
        with urllib.request.urlopen(URL, timeout=30) as response, pending.open('xb') as out:
            count = 0
            for block in iter(lambda: response.read(65536), b''):
                count += len(block)
                if count > 700000:
                    raise RuntimeError('libass download bound exceeded')
                out.write(block)
            out.flush()
            os.fsync(out.fileno())
        if count != 647066 or sha256_file(pending) != SHA:
            raise RuntimeError('Publisher SHA-256/size mismatch')
        os.link(pending, archive)
    if sha256_file(archive) != SHA:
        raise RuntimeError('Retained source changed')
    source = AREA / ('source-' + VERSION)
    if not source.exists():
        source.mkdir()
        total = 0
        with tarfile.open(archive) as tar:
            members = tar.getmembers()
            if len(members) > 4000:
                raise RuntimeError('Archive member bound')
            for member in members:
                parts = Path(member.name).parts
                if not parts or parts[0] != 'libass-' + VERSION or '..' in parts or member.name.startswith('/'):
                    raise RuntimeError('Unsafe archive path')
                relative = Path(*parts[1:])
                if not parts[1:]:
                    continue
                target = source / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile() and member.size <= 16 * 1024**2:
                    total += member.size
                    if total > 32 * 1024**2:
                        raise RuntimeError('Expanded source bound')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with tar.extractfile(member) as incoming, target.open('xb') as out:
                        out.write(incoming.read())
                    target.chmod(member.mode & 0o755)
                else:
                    raise RuntimeError('Non-regular source member')
    build_dir = AREA / 'build'
    build_dir.mkdir(exist_ok=True)
    flags = ['--prefix=' + str(PREFIX), '--disable-shared', '--enable-static', '--disable-fontconfig', '--enable-coretext', '--disable-test']
    pkg_path = '/opt/homebrew/lib/pkgconfig:/opt/homebrew/share/pkgconfig'
    env = {**os.environ, 'PKG_CONFIG': str(PKG), 'PKG_CONFIG_PATH': pkg_path,
           'CLANG_MODULE_CACHE_PATH': str(AREA / 'clang-cache')}
    dependency_flags = []
    for variable, package, include, library in (
        ('FREETYPE', 'freetype', 'freetype2', 'freetype'),
        ('FRIBIDI', 'fribidi', 'fribidi', 'fribidi'),
        ('HARFBUZZ', 'harfbuzz', 'harfbuzz', 'harfbuzz')):
        dependency = Path('/opt/homebrew/opt') / package
        if not (dependency / 'lib' / ('lib' + library + '.dylib')).is_file():
            raise RuntimeError('Required installed library missing: ' + package)
        env[variable + '_CFLAGS'] = '-I' + str(dependency / 'include' / include)
        env[variable + '_LIBS'] = '-L' + str(dependency / 'lib') + ' -l' + library
        dependency_flags.append(env[variable + '_LIBS'])
    run(['/bin/sh', source / 'configure', *flags], cwd=build_dir, env=env)
    run(['/usr/bin/make', '-j2'], cwd=build_dir, env=env)
    staging = AREA / 'destdir'
    run(['/usr/bin/make', 'DESTDIR=' + str(staging), 'install'], cwd=build_dir, env=env)
    installed = staging / str(PREFIX).lstrip('/')
    pc = installed / 'lib/pkgconfig/libass.pc'
    original = pc.read_text()
    (AREA / 'upstream-libass.pc').write_text(original)
    # Link the private static archive but resolve its dependencies through their
    # existing absolute Homebrew install names; preserve CoreText frameworks.
    dependency_flags = ' '.join(dependency_flags)
    original_lines = original.splitlines()
    framework_flags = ' '.join(line.split(':', 1)[1].strip() for line in original_lines if line.startswith('Libs.private:'))
    pc.write_text('prefix=' + str(PREFIX) + '\nName: libass\nDescription: Portable ASS subtitle renderer\nVersion: ' + VERSION +
                  '\nLibs: -L' + str(PREFIX / 'lib') + ' -lass ' + dependency_flags + ' ' + framework_flags +
                  '\nCflags: -I' + str(PREFIX / 'include') + '\n')
    licence = installed / 'share/licenses/libass/COPYING'
    licence.parent.mkdir(parents=True, exist_ok=True)
    licence.write_bytes((source / 'COPYING').read_bytes())
    write_json(installed / 'install.json', {'version': VERSION, 'url': URL, 'archive_sha256': SHA,
        'archive_bytes': archive.stat().st_size, 'library_sha256': sha256_file(installed / 'lib/libass.a'),
        'licence_sha256': sha256_file(licence), 'configure_flags': flags, 'pkg_config': pc.read_text(),
        'source_license': 'ISC', 'font_provider': 'CoreText', 'text_shaping': 'HarfBuzz + FriBidi'})
    rename_directory_new(installed, PREFIX)

def main():
    check_mounts(AREA)
    if '--build-child' in sys.argv:
        build()
        return 0
    if (PREFIX / 'install.json').is_file():
        saved = json.loads((PREFIX / 'install.json').read_text())
        if sha256_file(PREFIX / 'lib/libass.a') != saved['library_sha256']:
            raise RuntimeError('Retained libass archive changed')
        print(json.dumps({'status': 'reused', 'prefix': str(PREFIX)}))
        return 0
    print(json.dumps({'affected_paths': [str(AREA), str(PREFIX)], 'estimated_memory': 1024**3,
                      'estimated_storage': 512 * 1024**2}), flush=True)
    AREA.mkdir(parents=True, exist_ok=True)
    settings = Settings.load(state=ROOT / '.runtime/libass-bootstrap')
    store = Store(settings)
    plan = {'kind': 'bootstrap_libass', 'spec': {'operation': 'bootstrap_libass', 'output': str(PREFIX / 'install.json')},
            'estimates': {'job_memory_bytes': 1024**3, 'output_budget_bytes': 512 * 1024**2}, 'timeout_seconds': 600}
    plan['plan_id'] = digest(plan)
    queued = store.enqueue(plan)
    if queued['status'] in ('failed', 'interrupted', 'cancelled'):
        store.retry(queued['id'])
    job = store.claim(queued['id'])
    if not job:
        raise RuntimeError('Bootstrap job is not claimable')
    directory = store.root / 'jobs' / job['id'] / ('attempt-%03d' % job['attempt'])
    directory.mkdir(parents=True)
    try:
        with host_lock(settings) as lock_fd:
            receipt = supervised([sys.executable, '-B', str(Path(__file__).resolve()), '--build-child'],
                'libass-build', job, directory, settings, snapshot(AREA), lock_fd, AREA, process_kind='tool')
        store.update(job['id'], 'completed', receipt=receipt)
    except BaseException as error:
        store.update(job['id'], 'failed', error={'code': 'bootstrap_failed', 'message': str(error)[:1000]})
        raise
    print(json.dumps({'status': 'completed', 'prefix': str(PREFIX), 'receipt': str(directory / 'libass-build.request.receipt.json')}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
