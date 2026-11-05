#!/usr/bin/python3 -B
"""Actual release/MCP evidence থেকে portable comparison ও bounded acceptance report।"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2 import engine
from ffv2.io import sha256_file, write_json
from ffv2.releases import ACTIVE, REQUIRED, package_files, read, verified


def main():
    parser = argparse.ArgumentParser()
    for name in ('acceptance', 'lifecycle', 'mcp', 'configuration', 'batch', 'soak_audit', 'formats_audit', 'hdr', 'installed_default', 'installed_consumer', 'connected'):
        parser.add_argument('--'+name.replace('_', '-'), required=True, type=Path)
    args = parser.parse_args()
    index_path = ROOT/'docs/verification/phase4-7-2026-11-03.json'
    markdown_path = ROOT/'docs/PHASE4-7-RESULTS.md'
    if index_path.exists() or markdown_path.exists():
        raise RuntimeError('Final report exists; retain original artifacts')
    acceptance = read(args.acceptance)
    files = package_files()
    pointer = read(ACTIVE)
    installed = verified(Path(pointer['manifest']))
    selected = engine.selection(verify_hashes=True)
    if (acceptance.get('status') != 'completed' or acceptance['package_files'] != files or installed['package_files'] != files or
            installed['version'] != '0.5.0' or installed['engine_selection_id'] != selected['selection_id'] or
            acceptance['engine_selection_id'] != selected['selection_id']):
        raise RuntimeError('Matching actual installed final code/engine acceptance required')
    reports, evidence = {}, {}
    def attach(name, path, expected_sha=None):
        path = path.resolve(strict=True)
        checksum = sha256_file(path)
        if expected_sha and checksum != expected_sha:
            raise RuntimeError('Evidence changed: '+name)
        value = read(path)
        if value.get('status') != 'completed' or any(row.get('status') != 'pass' for row in value.get('tests', {}).values()):
            raise RuntimeError('Completed passing report required: '+name)
        reports[name] = value
        evidence[name] = {'path': str(path), 'sha256': checksum}
    for name in REQUIRED:
        row = acceptance['gates'][name]
        if row['status'] != 'pass':
            raise RuntimeError('Release gate did not pass: '+name)
        attach(name, Path(row['path']), row['sha256'])
    for name in ('lifecycle', 'mcp', 'configuration', 'batch', 'soak_audit', 'formats_audit', 'hdr', 'installed_default', 'installed_consumer', 'connected'):
        attach(name, getattr(args, name))
    if reports['unit_tests']['package_files'] != files or len(reports['unit_tests']['runs']) != 2:
        raise RuntimeError('Final two-runtime package regression required')
    if len(reports['lifecycle']['tests']) != 9 or reports['lifecycle']['final']['release_id'] != installed['release_id']:
        raise RuntimeError('Actual nine-case release lifecycle required')
    if reports['mcp'].get('server_info', {}).get('version') != '0.5.0' or not reports['mcp'].get('client_configuration'):
        raise RuntimeError('Final configured installed MCP connection required')
    if not reports['configuration'].get('unrelated_settings_unchanged'):
        raise RuntimeError('Preserved unrelated client configuration proof required')
    defaults = reports['installed_default']
    if (defaults.get('launcher') != str(Path.home()/'.local/bin/ffv2') or len(defaults.get('checks', {})) != 4 or
            any(not row.get('passed') or row.get('engine_selection_id') != installed['engine_selection_id'] for row in defaults['checks'].values())):
        raise RuntimeError('Actual installed default CLI four-profile proof required')
    if (reports['installed_consumer'].get('launcher') != str(Path.home()/'.local/bin/ffv2') or
            reports['installed_consumer'].get('engine_selection_id') != installed['engine_selection_id'] or
            len(reports['installed_consumer']['tests']) != 3):
        raise RuntimeError('Actual installed exec→Studio consumer/recovery proof required')
    for gate in ('consumer', 'installed_consumer'):
        for name, expected in reports[gate]['consumer_sources'].items():
            if sha256_file(Path(name)) != expected:
                raise RuntimeError('Existing consumer source changed since actual integration proof')
    for name in ('soak_audit', 'formats_audit'):
        audit = reports[name]
        if sha256_file(Path(audit['source_report'])) != audit['source_sha256']:
            raise RuntimeError('Supplement source report changed: '+name)
    analysis = reports['performance']
    timing_path = Path(analysis['source_report'])
    if sha256_file(timing_path) != analysis['source_sha256']:
        raise RuntimeError('Timing source changed')
    timing = read(timing_path)
    transition = acceptance['version_transition']
    before_files = transition['before_package_files']
    if (transition['changed_files'] != ['ffv2/__init__.py', 'pyproject.toml'] or
            sorted(key for key in files if files[key] != before_files[key]) != transition['changed_files']):
        raise RuntimeError('Only documented RC→final version literals may differ')
    before_sdk = {Path(k).name: v for k,v in before_files.items() if k.startswith('ffv2/')}
    if timing['package_source_sha256']['candidate-native'] != before_sdk or timing['status'] != 'completed' or timing['trials'] != 5:
        raise RuntimeError('Measured same functional RC implementation required')
    if len(timing['cases']) != 72 or sum(not row['warmup'] for row in timing['cases']) != 60:
        raise RuntimeError('Expected twelve excluded warmups and sixty measured outputs')
    seen_sources = set()
    for profile in timing['profiles'].values():
        if profile['input'] not in seen_sources:
            if sha256_file(Path(profile['input'])) != profile['source_sha256']:
                raise RuntimeError('Actual production source changed since benchmark')
            seen_sources.add(profile['input'])
    for profile in timing['profiles']:
        if not analysis['comparisons'][profile+'/candidate-native']['promotion_allowed']:
            raise RuntimeError('Software speed/quality promotion gate failed: '+profile)
        for label in timing['configurations']:
            rows = [row for row in timing['cases'] if row['profile'] == profile and row['label'] == label and not row['warmup']]
            if len(rows) != 5 or len({row['sha256'] for row in rows}) != 1:
                raise RuntimeError('Each software quality representative must cover five identical measured outputs')
    peaks = {}
    for row in timing['cases']:
        output, receipt_path = Path(row['output']), Path(row['receipt'])
        if sha256_file(output) != row['sha256']:
            raise RuntimeError('Retained benchmark output changed')
        receipt = read(receipt_path)
        if receipt['output_sha256'] != row['sha256'] or receipt['validation']['full_decode']['status'] != 'completed':
            raise RuntimeError('Actual full-decode/output receipt mismatch')
        expected_frames = timing['seconds']*timing['profiles'][row['profile']].get('fps', 30)
        if int(receipt['validation']['full_decode']['last_progress']['frame']) != expected_frames:
            raise RuntimeError('Actual benchmark full-decode frame count mismatch')
        if not row['warmup']:
            sampled_peak = max(receipt['encoding']['peak_job_memory_bytes'], receipt['validation']['full_decode']['peak_job_memory_bytes'])
            peaks.setdefault(row['profile']+'/'+row['label'], []).append(sampled_peak)
    evidence['timing'] = {'path': str(timing_path), 'sha256': sha256_file(timing_path), 'actual_outputs_rehashed': 72}
    counts = {name: len(value.get('tests', {})) for name,value in reports.items() if value.get('tests')}
    index = {'schema_version': 1, 'status': 'completed', 'maintainer': 'Jillur Rahman', 'created_at': time.time(),
             'release_id': installed['release_id'], 'version': installed['version'], 'package_files': files,
             'engine_selection_id': selected['selection_id'], 'native_files': selected['files'], 'evidence': evidence,
             'acceptance': {'path': str(args.acceptance.resolve()), 'sha256': sha256_file(args.acceptance)},
             'test_counts': counts, 'unit_runs': reports['unit_tests']['runs'], 'comparisons': analysis['comparisons'],
             'summary': timing['summary'], 'sampled_job_peak_median_bytes': {key: statistics.median(value) for key,value in peaks.items()},
             'version_transition': transition,
             'scope': 'Four bounded local phases; timing measured on functionally identical RC; final version independently regressed. Git/tag completion is audited after report publication.'}
    names = {'bbb-1080': 'BBB 1920×1080 / 30 fps', 'bbb-2160': 'BBB 3840×2160 / 30 fps',
             'bbb-2160-to1080': 'BBB 4K → 1920×1080', 'tos-liveaction': 'Tears of Steel 1920×800 / 24 fps'}
    lines = ['# Phase 4–7 — সম্পূর্ণ স্থানীয় comparison ও acceptance', '', 'Maintainer: **Jillur Rahman**। ৩ নভেম্বর ২০২৬। Local release **0.5.0**।', '',
             '## Performance: দীর্ঘ বাস্তব media', '',
             'প্রতি কাজ 60s media, start=60s। একই Mac-এ seeded interleaving; প্রতি profile/configuration একটি excluded warmup ও পাঁচটি measured paired trial। Full pipeline-এ probe, queue, encode, full strict decode, SHA-256 ও atomic publish আছে। মোট 72 output-এর checksum আবার মিলেছে; 60 measured output-এর প্রতি software group-এর পাঁচটি file একই bytes।', '',
             '| বাস্তব workload | v0.4 workflow / native | নতুন workflow / native | নতুন workflow / Stock | আগের workflow থেকে সময় কম | Native/Stock সময় অনুপাত |',
             '|---|---:|---:|---:|---:|---:|']
    for profile in timing['profiles']:
        base, native, stock = [timing['summary'][profile+'/'+label] for label in ('baseline-native', 'candidate-native', 'candidate-stock')]
        row = analysis['comparisons'][profile+'/candidate-native']
        ratio = native['total_seconds']/stock['total_seconds']
        lines.append('| '+names[profile]+f" | {base['total_seconds']:.4f}s | {native['total_seconds']:.4f}s | {stock['total_seconds']:.4f}s | {row['time_reduction_percent']:.2f}% | {ratio:.4f} |")
    lines += ['', 'Native/Stock অনুপাত <1 হলে native কম সময় নিয়েছে। নিচের paired interval 1 অতিক্রম করলে ওই engine difference অনিশ্চিত; Stock-এর তুলনায় native-এর universal speed advantage প্রমাণিত নয়। v0.4 baseline ও নতুন workflow একই নতুন native binary ব্যবহার করে, তাই প্রথম দুটি column workflow/thread-pool পরিবর্তন মাপে। Stock column-এ একই নতুন workflow/tuning থাকে।', '',
              '| Workload | নতুন/আগের workflow 95% ratio | Native/Stock 95% ratio | ΔVMAF | ΔPSNR-Y dB | ΔSSIM |', '|---|---:|---:|---:|---:|---:|']
    for profile in timing['profiles']:
        row, core = analysis['comparisons'][profile+'/candidate-native'], analysis['comparisons'][profile+'/native_vs_stock']
        lo, hi = row['paired_bootstrap_ratio_95_percent']; elo, ehi = core['paired_bootstrap_ratio_95_percent']; q = row['quality_deltas']
        lines.append('| '+names[profile]+f" | {lo:.4f}–{hi:.4f} | {elo:.4f}–{ehi:.4f} | {q['vmaf']:+.6f} | {q['psnr_y']:+.6f} | {q['ssim']:+.8f} |")
    lines += ['', 'সব চার software profile আগে নির্ধারিত ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05 dB, ΔSSIM≥−0.00001, size ratio≤1.02, faster median ও paired upper bound<1 gate পাস করেছে। প্রতি profile-এর সব 1800/1440 frame aligned reference-এ মাপা; quality reuse শুধু একই output SHA/source/range-এ। এটি নতুন compression algorithm নয়।', '',
              '## Encode, validation ও output size', '', '| Workload | Native encode median | Native full-decode median | Baseline bytes | Native bytes | Size পরিবর্তন |', '|---|---:|---:|---:|---:|---:|']
    for profile in timing['profiles']:
        b, n = [timing['summary'][profile+'/'+label] for label in ('baseline-native', 'candidate-native')]
        lines.append('| '+names[profile]+f" | {n['encode_seconds']:.4f}s | {n['decode_seconds']:.4f}s | {int(b['bytes']):,} | {int(n['bytes']):,} | {(n['bytes']/b['bytes']-1)*100:+.3f}% |")
    lines += ['', '| Workload | v0.4/native sampled peak median | নতুন/native sampled peak median | নতুন/Stock sampled peak median |', '|---|---:|---:|---:|']
    for profile in timing['profiles']:
        values = [statistics.median(peaks[profile+'/'+label])/1024**2 for label in ('baseline-native', 'candidate-native', 'candidate-stock')]
        lines.append('| '+names[profile]+' | '+' | '.join(f'{value:.2f} MiB' for value in values)+' |')
    lines += ['', 'Peak column প্রতি measured job-এর encoding/validation sampled tree peak-এর median; পুরো computer-এর memory বা instantaneous GPU peak নয়। CPU energy/power মাপা হয়নি। এই tuning parallelism বাড়িয়ে সময় কমায়; sampled peak memory আগের workflow-এর চেয়ে বেশি হয়েছে।', '',
              'নির্বাচিত M4 Max long software preset-এ encoder=4, decoder=2, validation=4; native filter=2, resize filter=4। HDR/deinterlace/VFR ও অন্য hardware/geometry-তে এই auto profile অন্ধভাবে প্রয়োগ হয় না। Hardware scaler-এর দীর্ঘ বাস্তব calibration-এ VMAF 6.45 কমেছিল; সেটি default-এ promote হয়নি। [Calibration ও negative results](PHASE4-RESULTS.md)।', '',
              '## Workflow ও reliability', '', '| Gate | Actual প্রমাণ |', '|---|---|',
              '| Phase 5 | 17 positive/error checks: normalized/copy concat packets/PTS, বাংলা SRT/ASS visible timing, PCM sample/gain/offset/loop/limiter, alpha/odd/16-bit PNG/matte, JPEG ও independent HDR pixels |',
              '| Phase 6 | 8 checkpoint/fault cases; corruption rebuild ও reuse, priority preemption, continuous audio packet equality, write-denial retry ও publish reconciliation |',
              '| Long batch | তিন বাস্তব 180s HD/UHD/live-action export; 540s total source, 15,120 decoded frames, sequential queue/idempotency |',
              '| Elapsed soak | 1,799.939s wall clock; 54,000 frame, 1,800.021s output, 355 durable records; sampled job-tree peak 149,440,192 bytes |',
              '| Existing consumer | Actual Studio cut/retime/fade/source-audio export; retained parts retry-তে identical output; tampered request refuse; existing source unchanged |',
              '| Installed CLI/consumer | User-local frozen CLI-তে চার long-profile output একই approved SHA; installed exec দিয়ে actual Studio export/retry/tamper checks |',
              '| Release lifecycle | Actual RC install, queued/running update fences, tampered candidate refusal, version-only update, stale MCP refusal, cross-code retry refusal, rollback checkpoint recovery ও final reactivation/launchers |',
              '| Installed MCP | Existing client entry ও installed final launcher-এ fresh real connection; typed advanced schema, queue/replay/priority/worker/PCM/mix/checksum/cancel/refusals |',
              '| Compatibility | 15 actual format imports/outputs; 2,893 local FATE records ও 15 selected external targets; 5,554 enabled external targets-এর পুরো suite নয় |', '',
              'দুই Python runtime-এর regression: '+', '.join(row['version']+' — '+str(row['tests'])+' tests' for row in reports['unit_tests']['runs'])+'। Native base 14 ও extended 21 check বর্তমান library identities-তে পাস। Runtime closure 38 file।', '',
              '## Scope ও provenance', '',
              'Timing frozen `0.5.0rc1` functional implementation-এ মাপা হয়েছে। Final `0.5.0`-এ শুধু দুই version literal বদলেছে; অন্য package bytes সমান, final দুই-runtime regression ও installed workflow পৃথকভাবে যাচাই হয়েছে। RC→final bridge original hashes/receipts রাখে।', '',
              'প্রথম interrupted run-এর চার excluded warmup retained; পরে canonical-path validation gap পাওয়া গেলে দ্বিতীয় run-এর 52 completed output ও stopped partial-ও রাখা হয়। শেষ timing table শুধুই সংশোধিত code-এর নতুন পূর্ণ run থেকে এসেছে। Homebrew libraries-এর device ID বদলালেও 38 content hash ও load path একই পাওয়া যায়; guard বজায় রেখে native/extended/MCP qualification ও explicit activation হয়েছে।', '',
              'Publisher HDR filename-যুক্ত excerpt-এ colour tags পাওয়া যায়নি; `hdr_metadata_required` refusal পাস করেছে। Positive HDR proof analytic pixel/tag tests; reference-display/perceptual mastering approval নয়। Studio acceptance technical; creative approval বা GUI deployment নয়। Current chat hot reload প্রমাণ নয়; configured fresh MCP connection প্রমাণিত।', '',
              'Default resource policy অপরিবর্তিত; task-এর explicit RAM waiver scoped। Sampled footprint, disk/mount/time/output checks ও sequential heavy work বহাল। 30-minute soak overnight/kernel guarantee নয়। Full external FATE, arbitrary camera corpus, cross-platform calibration, reproducible public distribution ও public release এই acceptance-এর বাইরে।', '',
              'Portable [evidence index](verification/phase4-7-2026-11-03.json), [contracts](PHASE5-7-DESIGN.md), [operations](OPERATIONS.md), [research/licences](PHASE4-RESEARCH.md), [acceptance register](../PHASE4-7.md)।', '', '## Original evidence', '', '| Evidence | Original report | SHA-256 |', '|---|---|---|']
    for name, record in evidence.items():
        lines.append('| '+name+' | ['+Path(record['path']).name+'](<'+record['path']+'>) | `'+record['sha256']+'` |')
    lines.append('')
    if package_files() != files:
        raise RuntimeError('Source changed during final evidence collection')
    write_json(index_path, index)
    markdown_path.write_text('\n'.join(lines))
    print(json.dumps({'index': str(index_path), 'report': str(markdown_path), 'release_id': installed['release_id'], 'counts': counts}))


if __name__ == '__main__':
    main()
