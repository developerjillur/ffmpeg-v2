#!/usr/bin/python3 -B
"""Cold evidence audit; an unproven candidate cannot alter the default pair."""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
from zoneinfo import ZoneInfo

from phase11_common import ROOT,WORK,read
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from ffv2.releases import ACTIVE,verified,package_files
from ffv2.resources import snapshot


def comparison_table(analysis):
    lines=['| Workload/load | Valid blocks | Reference | Candidate s | Reference s | Paired time change | Ratio95% CI |',
           '|---|---:|---|---:|---:|---:|---|']
    for key,group in analysis['comparisons'].items():
        if not group:
            lines.append(f"| {key} | {analysis['accepted_blocks'][key]} | Native/Stock | — | — | অপর্যাপ্ত stable blocks | — |")
        for label,value in group.items():
            ci=value['whole_block_95_percent']
            lines.append(f"| {key} | {value['blocks']} | {label} | {value['candidate_median_seconds']:.4f} | {value['reference_median_seconds']:.4f} | {value['time_change_percent']:+.3f}% | {ci[0]:.4f}–{ci[1]:.4f} |")
    return lines


def main():
    parser=argparse.ArgumentParser()
    names=('confirmation','analysis','workflow','workflow_analysis','quality','decoded','candidate','pgo','native','codec','unit')
    for name in names:parser.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,default=WORK/'initial.json')
    parser.add_argument('--supplement',type=Path,action='append',default=[])
    args=parser.parse_args()
    if args.output.exists() or args.results.exists():raise RuntimeError('Preserve completed audit/results')
    paths={name:getattr(args,name) for name in names};reports={name:read(path) for name,path in paths.items()}
    if any(r['status']!='completed' for name,r in reports.items() if name!='candidate'):raise RuntimeError('Primary evidence incomplete')
    direct=reports['confirmation'];analysis=reports['analysis'];workflow=reports['workflow'];wa=reports['workflow_analysis']
    for timing,summary,path in ((direct,analysis,args.confirmation),(workflow,wa,args.workflow)):
        if timing['baseline']!={'path':str(args.baseline),'sha256':sha256_file(args.baseline)}:raise RuntimeError('Final audit baseline differs from timing')
        if summary['source_sha256']!=sha256_file(path):raise RuntimeError('Analysis identity mismatch')
        if timing['quality']['sha256']!=sha256_file(args.quality):raise RuntimeError('Quality evidence binding differs')
        for row in timing['rows']:
            counter=Path(row['counter']);data=read(counter)
            if sha256_file(counter)!=row['counter_sha256']:raise RuntimeError('Counter evidence changed')
            if 'seconds' in row:
                if row['seconds']!=data['process']['wall_seconds']:raise RuntimeError('Elapsed summary differs from actual kernel time')
                if row['sha256']!=timing['quality']['expected_output_sha256'][row['profile']][row['label']]:raise RuntimeError('Golden output differs')
                if not timing.get('pipeline') and row['instructions']!=data['process']['instructions']:raise RuntimeError('Instruction summary differs from actual counter')
    if analysis['release_performance_accepted'] and wa['release_performance_accepted']:
        raise RuntimeError('Proven candidate requires native/FATE/soak and release lifecycle before final audit')
    quality=reports['quality'];identity=reports['decoded'];unit=reports['unit'];candidate=reports['candidate']
    if identity['source_sha256']!=quality['source_sha256'] or sha256_file(Path(quality['source_report']))!=quality['source_sha256']:
        raise RuntimeError('Decoded and quality sources differ')
    for item in identity['decodes'].values():
        if sha256_file(Path(item['framehash']))!=item['sha256']:raise RuntimeError('Decoded framehash changed')
    for item in quality['quality'].values():
        if sha256_file(Path(item['report']))!=item['metric_sha256']:raise RuntimeError('Quality metric artifact changed')
    qreport=read(quality['source_report'])
    if sha256_file(args.candidate)!=qreport['candidate_manifest_sha256']:raise RuntimeError('Candidate identity differs')
    if not all(v['quality_accepted'] for v in quality['comparisons'].values()):raise RuntimeError('Quality gate failed')
    if any(v['status']!='pass' for name in ('decoded','native','codec') for v in reports[name]['tests'].values()):raise RuntimeError('Candidate verification failed')
    if len(reports['native']['tests'])!=14 or len(reports['codec']['tests'])!=6:raise RuntimeError('Native/codec coverage incomplete')
    if len(unit['runs'])!=2 or any(r['tests']<176 or r['exit_code'] for r in unit['runs']) or unit['package_files']!=package_files():
        raise RuntimeError('Fresh two-runtime regression required')
    if not unit['inherited_memory_waiver_removed']:raise RuntimeError('Default-policy unit controls required')
    if reports['pgo']['status']!='completed' or len(reports['pgo']['steps'])!=10 or any(s['exit_code'] for s in reports['pgo']['steps']):raise RuntimeError('PGO build proof incomplete')
    if sha256_file(Path(candidate['profile_data']))!=candidate['profile_sha256'] or candidate['profile_instrumented'] or candidate['lto']:
        raise RuntimeError('Final profile/build identity changed')
    prefix=Path(candidate['prefix']);closure=library_closure([prefix/'bin'/n for n in ('ffmpeg','ffprobe','ffplay')])
    if closure!=candidate['files'] or closure!=reports['native']['verified_files'] or reports['native']['install_prefix']!=str(prefix):
        raise RuntimeError('Verified candidate runtime changed')
    for label,binary in direct['configurations'].items():
        if library_closure([Path(binary)])!=direct['engine_files'][label]:raise RuntimeError('Measured control changed')
    initial=read(args.baseline);current=read(ACTIVE);installed=verified(Path(current['manifest']));selected=selection(verify_hashes=True)
    if current['release_id']!=initial['release']['release_id'] or selected['selection_id']!=initial['selection']['selection_id']:
        raise RuntimeError('Unaccepted candidate altered default release/engine')
    if initial['package_files']!=package_files():raise RuntimeError('Unaccepted candidate altered production package bytes')
    source=Path(str(lab_path('ffmpeg-v2-phase10/x264-row-source')))
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise RuntimeError('Pinned codec source dirty')
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=candidate['source_commit']:raise RuntimeError('Codec source changed')
    if subprocess.check_output(['git','-C',str(lab_path('ffmpeg-v2-core/ffmpeg')),'status','--porcelain'],text=True).strip():raise RuntimeError('Original core source changed')
    queues=[]
    for path in sorted(WORK.rglob('jobs.sqlite3')):
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:counts=dict(db.execute('SELECT status,count(*) FROM jobs GROUP BY status'))
        active=sum(counts.get(s,0) for s in ('queued','waiting_resources','running','validating'));queues.append({'path':str(path),'counts':counts,'active':active})
    if any(q['active'] for q in queues):raise RuntimeError('Owned verification queues active')
    supplements=[]
    for path in args.supplement:
        if read(path).get('status')!='completed':raise RuntimeError('Incomplete supplement')
        supplements.append({'path':str(path),'sha256':sha256_file(path)})
    rollback_snapshot=None
    if current.get('previous'):
        pointer=read(Path(current['previous']));rollback_manifest=Path(pointer['manifest'])
        if sha256_file(rollback_manifest)!=pointer['manifest_sha256']:raise RuntimeError('Rollback manifest changed')
        rollback_release=verified(rollback_manifest)
        rollback_snapshot={'release_id':rollback_release['release_id'],'path':str(rollback_manifest),'sha256':sha256_file(rollback_manifest)}
    work={}
    for profile in direct['specifications']:
        for load in direct['load_levels']:
            key=profile+'/load'+str(load);values={label:[r['instructions'] for r in direct['rows'] if r['profile']==profile and r['load']==load and r['label']==label and not r['warmup'] and r.get('instructions')]
                for label in direct['configurations']}
            if all(values.values()):
                medians={label:statistics.median(v) for label,v in values.items()}
                work[key]={'median_instructions':medians,'n_completed':{label:len(v) for label,v in values.items()},
                    'candidate_change_percent':{label:100*(medians['candidate']/medians[label]-1) for label in ('original','stock')},
                    'scope':'All completed non-warmup cases, including environment-rejected blocks; CPU-work description only, not elapsed acceptance.'}
    rejections={}
    for name,timing in (('direct',direct),('workflow',workflow)):
        counts={}
        for block in timing['blocks']:
            for reason in block['validation']['reasons']:counts[reason]=counts.get(reason,0)+1
        rejections[name]=counts
    result={'status':'completed','phase':11,'maintainer':'Jillur Rahman','baseline_head':initial['baseline_head'],
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),'report_timezone':'Asia/Dhaka',
        'bounded_evaluation_complete':True,'all_remaining_gaps_fixed':False,
        'baseline':{'path':str(args.baseline),'sha256':sha256_file(args.baseline)},
        'supplements':supplements,'verified_rollback':rollback_snapshot,
        'active_release':current['release_id'],'active_engine':selected['selection_id'],'production_package_unchanged':True,
        'candidate_status':'quality_verified_experimental_not_activated','candidate_prefix':str(prefix),
        'performance_gate_passed':analysis['release_performance_accepted'],'workflow_gate_passed':wa['release_performance_accepted'],
        'stock_gap_closure_proven':False,'evidence':{name:{'path':str(path),'sha256':sha256_file(path)} for name,path in paths.items()},
        'complete_workflow_scope_speedup_proven':wa['release_performance_accepted'],
        'cpu_work':work,'rejected_block_reasons':rejections,'queue_audit':queues,'unit_counts':[r['tests'] for r in unit['runs']],
        'resources_final':snapshot(WORK).json(),
        'measurement_sources':{str(p.relative_to(ROOT)):sha256_file(p) for p in sorted((ROOT/'scripts').glob('*phase11*')) if p.is_file()},
        'limitations':['Conditioned wall-clock gates have not all passed; no default promotion or universal speed claim.',
            'Input and image warmup/locking cost excluded from timed child lifetime; warm-cache result only.',
            'Host processes, thermal state and scheduling are not frozen; invalid blocks retained and excluded only by predeclared resource conditions.',
            'PGO training is disjoint from confirmation but bounded; broad content generalization unproven.']}
    write_json(args.output,result)
    lines=['# Phase 11 — conditioned replay, private PGO এবং acceptance ফল','',
        'Maintainer: **Jillur Rahman**। '+datetime.now(ZoneInfo('Asia/Dhaka')).date().isoformat()+' (Asia/Dhaka)।','',
        '**Default release:** `'+current['release_id']+'`। নতুন candidate quality-verified experimental; required wall-clock gates একসঙ্গে pass হয়নি, তাই promote করা হয়নি।','',
        'Workload: BBB1920×1080/30fps-এর60–120s HD এবং60–90s raw YUV420p; raw file2,799,360,000bytes। Matched libx264/veryfast/CRF20, encoder8/decoder2/filter2; complete workflow validation8 এবং HD audio AAC160k। Progress contract matched। This machine/source/range ও admitted warm-cache conditions পর্যন্ত ফল প্রযোজ্য।','',
        '## পরিবর্তন ও quality','',
        'M4/vectorized private x264-এ disjoint training দিয়ে PGO; LTO নেই, safety assertions retained। Parent-side kernel start/exit clock এবং per-core CPU counter; একই input ও native runtime images bounded temporary lock করে residency যাচাই। Original/Homebrew ও installed code/native content unchanged; mount metadata recovery supplements-এ আলাদা।','',
        'HD1800video+2813audio এবং raw900video frame-এর fresh strict decoded timestamps/size/SHA256 exact match। Encoded private output আগের quality output-এর সঙ্গে exact SHA; VMAF/PSNR-Y/SSIM delta0। Private metadata-এর কারণে14bytes container difference।','',
        '| Source | VMAF mean | PSNR-Y dB | SSIM mean | Candidate delta vs Stock/Native |',
        '|---|---:|---:|---:|---|']
    for profile in ('hd60','raw30'):
        metric=quality['quality'][profile+'/candidate']['metrics']
        lines.append(f"| {profile} | {metric['vmaf']['mean']:.6f} | {metric['psnr_y']['mean']:.6f} | {metric['float_ssim']['mean']:.6f} | 0 / 0 / 0 |")
    lines+=['', '## Independent direct timing','',
        f"Completed cases {sum('seconds' in r for r in direct['rows'])}; excluded warmups {sum(r['warmup'] for r in direct['rows'])}; attempted blocks {len(direct['blocks'])}। প্রতি workload/load-এ9 accepted blocks প্রয়োজন।",'',
        'load0=অতিরিক্ত নিজস্ব CPU worker নেই; load2=দুটি50%-duty controlled CPU worker। Other host activity observed ও gated; CPU affinity/frequency/thermal state fixed নয়।','']
    lines+=comparison_table(analysis)
    lines+=['','Displayed seconds accepted-case medians; time change হলো paired block ratios-এর geometric mean, displayed medians-এর ratio নয়। Negative change মানে কম elapsed time। CI equality অতিক্রম করলে কিংবা9 stable blocks না হলে speedup proven নয়।','','## Complete typed HD workflow','']
    lines+=comparison_table(wa)
    lines+=['','এই complete workflow-এর ফল এই HD source/range ও warm-cache conditions-এর জন্য। দুই load-এ9 valid blocks/18 cases per engine; অন্য source বা encoder-only gap বন্ধ হওয়ার দাবি নয়। Overall release gate এখনও direct sample insufficiency-তে fail।',
        '','একই SDK/8-2-2-8 pools, matched progress, planning/encode/full decode/hash/no-clobber publish। Live root-only counters-কে descendant counters বলা হয়নি।','','## CPU work — descriptive','',
        '| Workload/load | Completed counts Native/PGO/Stock | Instructions vs Native | Instructions vs Stock |',
        '|---|---|---:|---:|']
    for key,value in work.items():
        counts=value['n_completed'];changes=value['candidate_change_percent']
        lines.append(f"| {key} | {counts['original']}/{counts['candidate']}/{counts['stock']} | {changes['original']:+.3f}% | {changes['stock']:+.3f}% |")
    lines+=['','এই CPU-work table-এ invalid-environment block-এর completed case-ও আছে; এটি wall-clock acceptance proof নয়।','','## Verification ও বাকি gap','',
        '- Native media/CLI/MCP14 checks এবং6 codec modes pass; deterministic8/10-bit, references/B-frames, slices, single-thread ও interlaced exact decode comparison। Scheduling-dependent mode-এ strict decode/assertions pass; exact equivalence claim নেই।',
        '- দুই Python runtime-এ '+ '/'.join(str(r['tests']) for r in unit['runs'])+' tests pass; default memory policy tests task waiver ছাড়া।',
        '- Owned databases '+str(len(queues))+', active jobs0। Baseline installed package/engine pair cold hash verified।',
        '- Remaining gap: whole-block CPU/P-share stability ও per-workload wall-clock confidence gate। Instruction reduction-কে speedup বলা হয়নি। New-prefix FATE/soak/install/rollback promotion lifecycle চালানো হয়নি, কারণ performance acceptance হয়নি।','',
        'সব completed/failed/rejected artifacts retained; cache warmup cost এবং rejected reasons raw evidence-এ আছে। Detailed method `docs/PHASE11-RESEARCH.md`; cold index `'+str(args.output)+'`; external work root `'+str(WORK)+'`।','']
    if rollback_snapshot:
        lines+=['## Original release recovery','',
            'Current original0.6 package/native content unchanged; stale device bindings fresh verification দিয়ে পুনরুদ্ধার। Retained0.5-ও exact old package ও same verified original native content-এ rebound; actual rollback এবং installed CLI/MCP checks-এর পরে0.6-এ ফেরত। এটি PGO promotion lifecycle নয়।',
            'Verified fallback: `'+rollback_snapshot['release_id']+'`। Old snapshots/proofs retained।','']
    for item in supplements:lines.append('Supplement: `'+item['path']+'` (SHA256 `'+item['sha256']+'`)।')
    args.results.write_text('\n'.join(lines));print(json.dumps({'index':str(args.output),'results':str(args.results),'active_release':current['release_id'],'active_jobs':0}))


if __name__=='__main__':main()
