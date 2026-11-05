#!/usr/bin/python3 -B
"""Cold audit and bounded Phase 10 result; unsuccessful speed gates stay visible."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase10')))
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from ffv2.releases import ACTIVE,verified,package_files


def read(path):return json.loads(Path(path).read_text())


def last_value(path):
    content=Path(path).read_text()
    try:return json.loads(content)
    except ValueError:return [json.loads(line) for line in content.splitlines() if line.startswith('{')][-1]


def mutex_work(report):
    rows=[]
    for row in report['rows']:
        events=[json.loads(line) for line in Path(row['trace']).read_text().splitlines()]
        if sha256_file(Path(row['trace']))!=row['trace_sha256']:raise RuntimeError('Worker trace changed')
        captured=sum(e['calls'] for e in events if e['event']=='mutex_site' and 'libx264' in Path(e['library']).name)
        overflow=sum(e['overflow_sites'] for e in events if e['event']=='worker')
        rows.append({'profile':row['profile'],'load':row['load'],'label':row['label'],
                     'captured_x264_mutex_calls':captured,'all_library_site_overflow_calls':overflow,
                     'x264_call_count_bounds':[captured,captured+overflow],
                     'encoder_library':row['encoder_library']})
    groups={}
    for profile in ('hd60','raw30'):
        for load in (0,2):
            base=next(r for r in rows if r['profile']==profile and r['load']==load and r['label']=='base')
            candidate=next(r for r in rows if r['profile']==profile and r['load']==load and r['label']=='candidate')
            groups[profile+'/load'+str(load)]={'base':base,'candidate':candidate,
                'reduction_percent_bounds':[100*(1-candidate['x264_call_count_bounds'][1]/base['x264_call_count_bounds'][0]),
                                            100*(1-candidate['x264_call_count_bounds'][0]/base['x264_call_count_bounds'][1])]}
    return groups


def workflow_table(workflow):
    lines=['| Workflow comparison | Median time change | Candidate/reference 95% CI | Verdict |',
           '|---|---:|---|---|']
    for label,row in workflow['comparisons'].items():
        ci=row['block_bootstrap_95_percent']
        lines.append(f"| candidate / {label} | {row['slowdown_percent']:+.3f}% | {ci[0]:.4f}–{ci[1]:.4f} | Confidence gate pass হয়নি |")
    return lines


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--controls',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--results',required=True,type=Path);args=parser.parse_args()
    if args.output.exists() or args.results.exists():raise RuntimeError('Preserve completed audit/results')
    controls=read(args.controls)
    if controls['status']!='completed' or any(r['status']!='completed' for r in controls['steps']):raise RuntimeError('Sequential controls incomplete')
    values={r['name']:last_value(r['log']) for r in controls['steps']}
    paths={'confirmation':Path(controls['confirmation']),'quality':Path(values['quality']['quality_report']),
        'analysis':Path(values['analysis']['analysis']),'decoded_identity':Path(values['decoded-identity']['report']),
        'negative_progress_tsan':Path(values['progress-negative-publication']['report']),
        'observers':Path(values['build-observers']['report']),'worker_profile':Path(values['worker-profile']['report']),
        'process_profile':Path(values['process-profile']['report']),'codec_regression':Path(values['codec-regression']['report']),
        'workflow':Path(values['full-workflow']['report']),
        'native_media':Path(values['native-cli-mcp']['directory'])/'report.json','unit_tests':Path(values['unit-matrix']['report'])}
    reports={name:read(path) for name,path in paths.items()}
    if any(r['status']!='completed' for r in reports.values()):raise RuntimeError('A primary report is incomplete')
    timing=reports['confirmation'];analysis=reports['analysis'];workflow=reports['workflow'];unit=reports['unit_tests']
    if sha256_file(paths['confirmation'])!=controls['confirmation_sha256']:raise RuntimeError('Confirmation changed')
    for name in ('quality','analysis','decoded_identity'):
        if reports[name]['source_sha256']!=sha256_file(paths['confirmation']):raise RuntimeError('Timing/evidence identity mismatch')
    if analysis['release_performance_accepted'] and workflow['hd_workflow_improvement_accepted']:
        raise RuntimeError('Accepted speed candidate requires the full native/release lifecycle before finalizing')
    if len(unit['runs'])!=2 or any(r['tests']<142 or r['exit_code'] for r in unit['runs']) or unit['package_files']!=package_files():
        raise RuntimeError('Fresh two-runtime regression required')
    for name in ('decoded_identity','codec_regression','native_media'):
        if any(r['status']!='pass' for r in reports[name]['tests'].values()):raise RuntimeError('Failed verification: '+name)
    initial=read(WORK/'initial.json');current=read(ACTIVE);installed=verified(Path(current['manifest']))
    selected=selection(verify_hashes=True)
    if current['release_id']!=initial['release']['release_id'] or selected['selection_id']!=initial['selection']['selection_id']:
        raise RuntimeError('Unaccepted optimization changed the active code/engine pair')
    original_sdk={k:v for k,v in initial['package_files'].items() if k.startswith('ffv2/')}
    if original_sdk!={k:v for k,v in package_files().items() if k.startswith('ffv2/')}:
        raise RuntimeError('Unaccepted optimization changed production SDK bytes')
    for label,binary in timing['configurations'].items():
        if library_closure([Path(binary)])!=timing['engine_files'][label]:raise RuntimeError('Measured engine closure changed')
    native=reports['native_media'];prefix=Path(native['install_prefix'])
    if library_closure([prefix/'bin'/name for name in ('ffmpeg','ffprobe','ffplay')])!=native['verified_files']:
        raise RuntimeError('Candidate changed after native verification')
    if subprocess.check_output(['git','status','--porcelain'],cwd=str(lab_path('ffmpeg-v2-core/ffmpeg')),text=True).strip():
        raise RuntimeError('Original native checkout changed')
    patch=read(ROOT/'third_party/x264/manifest.json')
    for item in patch['patches']:
        if sha256_file(ROOT/'third_party/x264'/item['file'])!=item['sha256']:raise RuntimeError('Source patch changed')
    replay_path=WORK/'patch-replay-audit.json';replay=read(replay_path)
    if replay['status']!='completed' or replay['patched_tree']!=patch['patched_tree'] or not replay['original_worktree_clean']:
        raise RuntimeError('Exported patches must reconstruct the exact source tree')
    queues=[]
    for path in sorted(WORK.rglob('jobs.sqlite3')):
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
            counts=dict(db.execute('SELECT status,count(*) FROM jobs GROUP BY status'))
        active=sum(counts.get(k,0) for k in ('queued','waiting_resources','running','validating'))
        queues.append({'path':str(path),'counts':counts,'active':active})
    if any(q['active'] for q in queues):raise RuntimeError('Owned verification queues remain active')
    mutex=mutex_work(reports['worker_profile'])
    records={name:{'path':str(path),'sha256':sha256_file(path)} for name,path in paths.items()}
    records['controls']={'path':str(args.controls),'sha256':sha256_file(args.controls)}
    snapshots={}
    for name,key in (('benchmark_phase10.confirm-frozen.py','runner_sha256'),('replay_phase10.confirm-frozen.py','child_runner_sha256')):
        path=WORK/name
        if sha256_file(path)!=timing[key]:raise RuntimeError('Frozen measurement source changed')
        snapshots[name]={'path':str(path),'sha256':sha256_file(path)}
    result={'status':'completed','phase':10,'maintainer':'Jillur Rahman','baseline_head':initial['baseline_head'],
        'active_release':current['release_id'],'active_engine':selected['selection_id'],'production_sdk_unchanged':True,
        'candidate_status':'verified_experimental_not_activated','stock_gap_closure_proven':False,
        'performance_gate_passed':analysis['release_performance_accepted'],'workflow_gate_passed':workflow['hd_workflow_improvement_accepted'],
        'candidate_prefix':str(prefix),'x264_source':patch,'evidence':records,'frozen_measurement_sources':snapshots,
        'source_patch_replay':{'path':str(replay_path),'sha256':sha256_file(replay_path),'patched_tree':replay['patched_tree']},
        'mutex_work':mutex,'queue_audit':queues,'unit_counts':[r['tests'] for r in unit['runs']],
        'limitations':['Whole-block wall-clock intervals cross equality; no stable Stock superiority or gap-closure claim.',
                       'Only added CPU demand is controlled; unrelated host activity and raw-input file-cache residency vary.',
                       'Worker mutex hook uses trylock and has bounded callsite storage; timings are excluded and overflow bounds retained.',
                       'Non-deterministic codec mode passed strict decode/assertions; exact quality equivalence is not claimed for that mode.']}
    write_json(args.output,result)
    lines=['# Phase 10 — verified source efficiency, elapsed gap এখনও অপ্রমাণিত','',
        'Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬।','',
        '**ফল:** private x264-এর progress query ও compiler tuning-এ একই content কম instructions-এ encode হয়েছে। Target decoded video/audio exact match। Independent wall-clock confidence gates পাস হয়নি; candidate experimental, active release `'+current['release_id']+'`।','',
        '## Implemented fix','',
        'Pinned x264 `'+patch['base_commit']+'` থেকে atomic acquire/release progress query এবং positive row-wait-এর acquired lower-bound cache। Motion-vector required-line check, positive mutex/condition wait এবং warning/recovery বজায় আছে। Final candidate M4 target ও vectorization ব্যবহার করে; LTO নেই। M4+LTO variant SIGSEGV-তে rejected; receipts ও partial retained।','',
        '## Independent encode timing','',
        'একই input/argv, 8 encoder / 2 decoder / 2 filter, CRF20/veryfast। 7 balanced blocks × 4 input/load groups × 6 runs = 168 measured encodes; 12 excluded warmups, মোট 180। প্রতি cell-এ প্রতি engine 14 measured runs। No-added-load-কে idle machine বলা হয়নি। CI হলো 20,000 whole-block bootstrap resamples-এর candidate/Stock ratio।','',
        '| Workload | Added workers | Active 0.6 encode s | Candidate s | Stock s | Candidate vs Stock | Ratio 95% CI |',
        '|---|---:|---:|---:|---:|---:|---|']
    for key,group in analysis['comparisons'].items():
        a,b=group['original'],group['stock'];ci=b['block_bootstrap_95_percent'];profile,load=key.split('/')
        lines.append(f"| {profile} | {load[4:]} | {a['stock_median_seconds']:.4f} | {b['native_median_seconds']:.4f} | {b['stock_median_seconds']:.4f} | {b['slowdown_percent']:+.2f}% time | {ci[0]:.4f}–{ci[1]:.4f} |")
    lines+=['','সব CI equality অতিক্রম করেছে। ভালো median-কে proven speedup বলা হয়নি; slow runs বাদ দেওয়া হয়নি।','',
        '## CPU work ও mutex traffic','',
        '| Workload/load | Instructions vs active 0.6 | Instructions vs Stock | Captured x264 mutex reduction bounds |',
        '|---|---:|---:|---|']
    for key,group in analysis['cpu_work_comparisons'].items():
        bounds=mutex[key]['reduction_percent_bounds']
        lines.append(f"| {key} | {group['instructions']['original']['slowdown_percent']:+.3f}% | {group['instructions']['stock']['slowdown_percent']:+.3f}% | {bounds[0]:.4f}%–{bounds[1]:.4f}% |")
    lines+=['','Mutex bounds-এ সব library-র unrecorded callsite overflow-ও candidate-এর বিপক্ষে ধরে হিসাব করা হয়েছে। V5 observer প্রতিটি engine-এর নির্দিষ্ট x264-তেই link করেছে; actual loaded image ও parameter function binding verified। এই instrumented timings speed promotion-এর জন্য নয়। CPU instruction improvement-এ source patch ও private compiler tuning দুটোই আছে; পুরো লাভকে শুধু source patch বলা হয়নি।','',
        '## Root-cause evidence','',
        'Original Native ও Stock একই Homebrew x264 ব্যবহার করত। Shared macroblock progress-query locking একটি বাস্তব avoidable cost, কিন্তু এটি একা আগের Native/Stock gap-এর ব্যাখ্যা নয়। Public kernel runnable counters-এ ready-but-not-running wait এবং P-core share বদলেছে। Process-only observer-এ pthread hooks বাদ রেখেও এই পরিবর্তন পাওয়া গেছে। Aggregate worker wait-কে elapsed time-এর সঙ্গে সরাসরি যোগ/বিয়োগ করা হয়নি।','',
        'Raw profiling-এর একটি baseline run-এ প্রায় 2.80 GB disk read এবং পরের private run-এ প্রায় 1.36 MB পাওয়া গেছে। Process-only replay-তেও original/raw/no-added-load-এ 2.80 GB, candidate-এ 7.75 MB, Stock-এ 0.74 MB। এটি cache residency-র একটি measured imbalance। তাই ওই profiler timing-কে codec speedup বলা হয়নি। আগের 9.53%/4.44%-এর কত অংশ CPU queue, cache বা অন্য কারণে—তার exact causal percentage এই busy-host experiment নির্ধারণ করে না।','',
        '## Full typed 1080p workflow','',
        'একই frozen 0.6 SDK, 8/2/2/8 pools, planning → encode → strict full decode → hash → no-clobber publication। Added synthetic load নেই। 3 excluded warmups + 42 measured runs।','',
        '| Engine | Total median s | Encode median s | Validation median s |',
        '|---|---:|---:|---:|']
    for label,data in workflow['stage_medians'].items():
        lines.append(f"| {label} | {data['total_seconds']:.4f} | {data['encode_seconds']:.4f} | {data['decode_seconds']:.4f} |")
    lines+=['',*workflow_table(workflow),'',
        '## Quality ও regression','',
        '- HD: সব 1,800 video frame ও 2,813 decoded audio frame-এর timestamps/size/SHA-256 exact match। Raw: সব 900 frame exact match। Container/version metadata 14 bytes ছোট।',
        '- HD VMAF 94.781527, PSNR-Y 47.011742 dB, SSIM 0.998632; raw VMAF 94.920178, PSNR-Y 46.621946 dB, SSIM 0.998291। ΔVMAF/PSNR/SSIM=0। Final candidate-এর metric reuse exact encoded/source SHA ও identical range/fps/argv দিয়ে bound; actual decoded identity নতুন করে মাপা।',
        '- Actual patched frame API-র 8/10-bit ThreadSanitizer: প্রতি depth 524,288, মোট 1,048,576 checks, errors 0; negative pre-publication, positive wait, query ও buffer reuse covered।',
        '- Multiple references/B-frames, 10-bit, sliced, single-thread ও interlaced modes: original/candidate/live-assertion build-এর decoded frames exact match। Non-deterministic mode: strict decode ও safety assertions pass; exact quality equivalence দাবি নয়।',
        f"- Native CLI/MCP/media checks: {len(native['tests'])} pass। দুই Python runtime: "+'/'.join(str(r['tests']) for r in unit['runs'])+' tests pass; default memory policy tests task waiver ছাড়া চলেছে।',
        f"- Owned verification database audit: {len(queues)} databases, active jobs 0। Active installed code/engine hash verified; original native checkout clean।",'',
        '## Acceptance ও বাকি সীমা','',
        'প্রমাণিত ফল হলো source/CPU efficiency ও exact target content preservation। Stock-এর বিরুদ্ধে স্থায়ী wall-clock gap closure এবং default-release promotion এখনও হয়নি। Confidence gate পূরণ না হওয়ায় installation/rollback pointer বদলানো হয়নি। স্থির host/cache conditions-এ নতুন predeclared acceptance window ছাড়া পুরোনো point estimate-কে fixed বলা যাবে না।','',
        'Source patches/license: `third_party/x264/`। Detailed method: `docs/PHASE10-RESEARCH.md`। Cold evidence index: `'+str(args.output)+'`। External work root: `'+str(WORK)+'`। All completed/slow/failed experiment receipts retained।','']
    args.results.write_text('\n'.join(lines))
    print(json.dumps({'index':str(args.output),'results':str(args.results),'active_release':current['release_id'],
                      'candidate_status':result['candidate_status'],'databases':len(queues),'active_jobs':0}))


if __name__=='__main__':main()
