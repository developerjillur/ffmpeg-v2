"""Source/tool-bound CFR segments; এক continuous audio pass ও durable retry।"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import time
import uuid

from .bindings import assert_sources
from .errors import FFV2Error
from .io import fingerprint, sha256_file, write_json
from .media import INPUT_LIMITS, probe_path, rational

REVISION = 1

def configure(plan):
    spec, video = plan['spec'], plan['source']['video']
    fps = spec.get('fps')
    if (spec['operation'] != 'transcode' or not fps or abs(rational(video.get('avg_frame_rate')) - fps) > .001 or
        abs(rational(video.get('r_frame_rate')) - fps) > .001 or rational(video.get('start_time')) != 0 or
        rational(plan['source']['format'].get('start_time')) != 0 or
        abs(rational((plan['source'].get('audio') or {}).get('start_time'))) > .001 or spec.get('deinterlace', 'off') != 'off'):
        raise FFV2Error('checkpoint_cfr_required', 'Checkpoint preset-এর জন্য zero-origin CFR video/audio ও একই explicit integer fps প্রয়োজন; VFR/offset source-এর সাধারণ transcode অপরিবর্তিত।')
    start, duration = spec.get('start', 0), plan['expected']['duration_seconds']
    if abs(start * fps - round(start * fps)) > .00001 or abs(duration * fps - round(duration * fps)) > .00001:
        raise FFV2Error('checkpoint_frame_grid', 'Checkpoint range source frame grid-এর সঙ্গে মেলাতে হবে।')
    frames, segment_frames = round(duration * fps), spec['checkpoint_seconds'] * fps
    count = math.ceil(frames / segment_frames)
    if count > 2048:
        raise FFV2Error('checkpoint_segment_budget', 'এক job-এ সর্বোচ্চ 2048 segments; checkpoint_seconds বাড়ান।')
    plan['checkpoint'] = {'revision': REVISION, 'fps': fps, 'frames': frames, 'segment_frames': segment_frames, 'segments': count}
    plan['expected']['video_frames'] = frames
    plan['estimates']['admission_output_budget_bytes'] = 2 * plan['estimates']['output_budget_bytes'] + 256 * 1024**2
    plan['warnings'].append('Checkpoint CFR timeline runtime-এ সম্পূর্ণ probe হয়; validated segments ও continuous AAC pass identity/hash মিলে তবেই reuse হয়।')

def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

def execute(plan, job, directory, settings, baseline, lock_fd, store, *, session=None):
    from .worker import supervised, validate_metadata, hash_guarded
    root = store.root / 'jobs' / job['id'] / 'checkpoints'
    root.mkdir(mode=0o700, exist_ok=True)
    if root.is_symlink():
        raise FFV2Error('checkpoint_path_changed', 'Checkpoint directory symlink হতে পারবে না।')
    manifest_path = root / 'manifest.json'
    cp = plan['checkpoint']
    manifest = {'revision': REVISION, 'plan_id': plan['plan_id'], 'segments': {}, 'audio': None, 'invalidated': []}
    if manifest_path.exists():
        if manifest_path.is_symlink() or manifest_path.stat().st_size > 8 * 1024**2:
            raise FFV2Error('checkpoint_invalid', 'Checkpoint manifest-এর file/size গ্রহণযোগ্য নয়।')
        manifest = json.loads(manifest_path.read_text())
        if manifest.get('plan_id') != plan['plan_id'] or manifest.get('revision') != REVISION:
            raise FFV2Error('checkpoint_identity_changed', 'Saved checkpoint source/spec/tool identity মেলেনি।')
    def save():
        write_json(manifest_path, manifest)
        sync_directory(root)
    deadline = time.monotonic() + plan['timeout_seconds']
    steps, reused, generated = [], [], []
    def run(argv, name, target, *, budget=None):
        assert_sources(plan)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FFV2Error('checkpoint_timeout', 'Checkpoint job-এর মোট time budget শেষ হয়েছে।', retryable=True)
        modified_job = {**job, 'plan': {**plan, 'estimates': {**plan['estimates'], 'output_budget_bytes': budget or plan['estimates']['output_budget_bytes']}}}
        receipt = supervised(argv, name, modified_job, directory, settings, baseline, lock_fd, target,
                             timeout=remaining, admission_budget=0, session=session)
        steps.append({'phase': name, 'receipt': receipt})
        return receipt
    def valid(record):
        if not record:
            return False
        path = Path(record['path'])
        if path.parent != root or path.is_symlink():
            raise FFV2Error('checkpoint_path_changed', 'Saved segment path private checkpoint directory-এর বাইরে।')
        return path.is_file() and fingerprint(path) == record['identity'] and sha256_file(path) == record['sha256']
    def publish(path, name, metadata, validation):
        checksum = hash_guarded(path, settings, baseline, store, job['id'])
        destination = root / (name + '-' + uuid.uuid4().hex[:12] + path.suffix)
        with path.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(path, destination, follow_symlinks=False)
        sync_directory(root)
        return {'path': str(destination), 'sha256': checksum, 'identity': fingerprint(destination), 'metadata': metadata,
                'validation': validation, 'attempt': job['attempt']}
    source_sha256 = hash_guarded(Path(plan['source']['path']), settings, baseline, store, job['id'])
    if manifest.get('source_sha256') and manifest['source_sha256'] != source_sha256:
        raise FFV2Error('checkpoint_source_changed', 'Saved segments-এর source content checksum বদলেছে; নতুন plan প্রয়োজন।')
    manifest['source_sha256'] = source_sha256
    save()
    # A full source frame schedule rejects VFR/missing frames instead of silently
    # resetting a variable timestamp grid independently in every segment.
    if not manifest.get('timeline_verified'):
        timeline = directory / 'source-timeline.csv'
        run([plan['binary']['ffprobe'], '-v', 'error', *INPUT_LIMITS, '-threads', '1', '-err_detect', 'explode',
             '-select_streams', 'v:0', '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time',
             '-of', 'compact=p=0:nk=0', '-o', str(timeline), plan['source']['path']], 'checkpoint-index', timeline, budget=256*1024**2)
        count, maximum = 0, 0.0
        if not timeline.is_file() or timeline.stat().st_size > 256*1024**2:
            raise FFV2Error('checkpoint_index_budget', 'Frame timeline index অনুপস্থিত বা size budget-এর বাইরে।')
        tolerance = max(.0011, rational(plan['source']['video'].get('time_base')) * 1.1)
        with timeline.open() as stream:
            for line in stream:
                fields = dict(part.split('=', 1) for part in line.strip().split('|') if '=' in part)
                if 'best_effort_timestamp_time' not in fields:
                    continue
                try:
                    point = float(fields['best_effort_timestamp_time'])
                except ValueError as error:
                    raise FFV2Error('checkpoint_cfr_required', 'প্রতি decoded source frame-এর timestamp প্রয়োজন।') from error
                delta = abs(point - count / cp['fps'])
                if not math.isfinite(point) or delta > tolerance:
                    raise FFV2Error('checkpoint_cfr_required', 'Source-এর সম্পূর্ণ decoded timeline constant frame grid নয়।')
                maximum = max(maximum, delta)
                count += 1
                if count > 6_000_000:
                    raise FFV2Error('checkpoint_index_budget', 'Source frame index budget-এর বাইরে।')
        if count < round(plan['spec'].get('start', 0)*cp['fps']) + cp['frames']:
            raise FFV2Error('checkpoint_source_short', 'Requested frame range-এর জন্য source frames কম।')
        manifest['timeline_verified'] = {'frames': count, 'max_timestamp_error': maximum, 'sha256': sha256_file(timeline), 'index': str(timeline)}
        save()
    # Remove only known output options from the typed single-source video plan.
    def video_argv(start, frames, target):
        result, index = [], 0
        argv = plan['argv']
        source_audio = plan['source']['audio']
        while index < len(argv):
            key = argv[index]
            if key == '-map' and source_audio and argv[index+1] == '0:' + str(source_audio['index']):
                index += 2
                continue
            if key in ('-c:a', '-b:a', '-threads:a', '-movflags'):
                index += 2
                continue
            if key in ('-ss', '-t', '-f'):
                value = format(start, '.12g') if key == '-ss' else format(frames / cp['fps'], '.12g') if key == '-t' else 'matroska'
                result.extend((key, value))
                index += 2
                continue
            if key == '<STAGING_OUTPUT>':
                result.extend(('-an', '-frames:v', str(frames), str(target)))
            else:
                result.append(key)
            index += 1
        return result
    for number in range(cp['segments']):
        key = str(number)
        record = manifest['segments'].get(key)
        if valid(record):
            reused.append(number)
        else:
            if record:
                manifest['invalidated'].append({'segment': number, 'record': record, 'reason': 'identity_or_checksum_changed'})
                del manifest['segments'][key]
                save()
            count = min(cp['segment_frames'], cp['frames'] - number*cp['segment_frames'])
            target = directory / ('segment-%04d.mkv' % number)
            start = plan['spec'].get('start', 0) + number*cp['segment_frames']/cp['fps']
            run(video_argv(start, count, target), 'segment-%04d' % number, target)
            media = probe_path(target, plan['binary']['ffprobe'])
            expected = {**plan['expected'], 'audio_codec': None, 'audio_streams': 0, 'duration_seconds': count/cp['fps'], 'video_frames': count}
            validate_metadata({**plan, 'expected': expected}, media)
            decoded = run([plan['binary']['ffmpeg'], '-v', 'error', '-nostdin', '-xerror', '-nostats', '-progress', 'pipe:1',
                *INPUT_LIMITS, '-threads', str(plan['runtime_tuning']['validation_threads']), '-err_detect', 'explode', '-i', str(target),
                '-map', '0:v:0', '-threads', '1', '-f', 'null', '-'], 'segment-check-%04d' % number, target)
            if int((decoded.get('last_progress') or {}).get('frame', -1)) != count:
                raise FFV2Error('checkpoint_frames_mismatch', 'পূর্ণ segment decode-এর frame count মেলেনি।')
            manifest['segments'][key] = publish(target, 'segment-%04d' % number, media, decoded)
            generated.append(number)
            save()
        store.progress(job['id'], {'phase': 'checkpoint', 'completed_segments': number+1, 'total_segments': cp['segments'], 'reused_segments': len(reused)})
        if store.cancelled(job['id']):
            raise FFV2Error('cancelled', 'Completed checkpoints রেখে job বাতিল হয়েছে।', exit_code=130)
        if store.higher_priority_waiting(job['id']):
            raise FFV2Error('checkpoint_yielded', 'Validated segment boundary-তে higher-priority job-এর জন্য queue-তে ফেরত গেছে।',
                            details={'manifest': str(manifest_path), 'completed_segments': number+1}, retryable=True, exit_code=75)
    if plan['source']['audio'] and not valid(manifest.get('audio')):
        if manifest.get('audio'):
            manifest['invalidated'].append({'audio': manifest['audio'], 'reason': 'identity_or_checksum_changed'})
        audio = directory / 'continuous-audio.m4a'
        run([plan['binary']['ffmpeg'], '-v', 'error', '-nostdin', '-n', '-xerror', '-nostats', '-progress', 'pipe:1', *INPUT_LIMITS,
            '-threads', '1', '-ss', str(plan['spec'].get('start', 0)), '-err_detect', 'explode', '-i', plan['source']['path'],
            '-map', '0:' + str(plan['source']['audio']['index']), '-vn', '-t', str(plan['expected']['duration_seconds']),
            '-c:a', 'aac', '-b:a', '160k', '-threads:a', '1', '-map_metadata', '-1', '-fs', str(plan['estimates']['output_budget_bytes']), str(audio)], 'continuous-audio', audio)
        metadata = probe_path(audio, plan['binary']['ffprobe'])
        decoded = run([plan['binary']['ffmpeg'], '-v', 'error', '-nostdin', '-xerror', '-threads', '1', '-err_detect', 'explode', '-i', str(audio), '-vn', '-f', 'null', '-'], 'continuous-audio-check', audio)
        manifest['audio'] = publish(audio, 'continuous-audio', metadata, decoded)
        save()
    manifest_file = directory / 'segments.ffconcat'
    text = 'ffconcat version 1.0\n'
    for number in range(cp['segments']):
        path = manifest['segments'][str(number)]['path']
        count = min(cp['segment_frames'], cp['frames']-number*cp['segment_frames'])
        text += "file '" + path.replace("'", "'\\''") + "'\nduration " + format(count/cp['fps'], '.12g') + '\n'
    with manifest_file.open('x') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    return {'manifest': str(manifest_path), 'manifest_sha256': sha256_file(manifest_path), 'reused_segments': reused,
            'generated_segments': generated, 'steps': steps, 'concat_manifest': str(manifest_file),
            'continuous_audio': (manifest.get('audio') or {}).get('path')}

def assembly(plan, checkpoint, target):
    argv = [plan['binary']['ffmpeg'], '-v', 'error', '-nostdin', '-n', '-xerror', '-nostats', '-progress', 'pipe:1',
            '-protocol_whitelist', 'file', '-format_whitelist', INPUT_LIMITS[-1] + ',concat', '-f', 'concat', '-safe', '0', '-auto_convert', '0',
            '-i', checkpoint['concat_manifest']]
    if checkpoint['continuous_audio']:
        argv += [*INPUT_LIMITS, '-i', checkpoint['continuous_audio']]
    argv += ['-map', '0:v:0']
    if checkpoint['continuous_audio']:
        argv += ['-map', '1:a:0']
    return argv + ['-c', 'copy', '-t', str(plan['expected']['duration_seconds']), '-map_metadata', '-1', '-map_chapters', '-1',
                   '-movflags', '+faststart', '-f', 'mp4', '-fs', str(plan['estimates']['output_budget_bytes']), str(target)]
