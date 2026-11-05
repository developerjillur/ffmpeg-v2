# Experimental optimization measurements

For the released product's **22.61% / 28.48% less elapsed time** comparison against
the prior Stock workflow preset, start with [released workflow results](WORKFLOW-RESULTS.md).
The research candidate below is a separate experiment and is not the basis of those claims.

Public 0.6.1 is a source/portability release. The following are historical Phase 11 measurements of an experimental PGO engine, not a rerun of the new public packaging. The candidate was **not promoted**.

## Exact Phase 11 comparisons

Negative change means less elapsed time. Seconds are accepted-case medians; paired time change is the geometric mean of whole-block ratios, not their median ratio. The release requires nine valid whole blocks in every workload/load group and an upper paired 95% ratio below 1 against **both** references, plus exact quality.

| Pipeline / workload | Reference | Valid / required | Candidate s | Reference s | Paired elapsed change | Ratio 95% interval | Group eligible |
|---|---|---:|---:|---:|---:|---|---|
| direct / hd60/load0 | original | 1 / 9 | — | — | Insufficient | — | No |
| direct / hd60/load0 | stock | 1 / 9 | — | — | Insufficient | — | No |
| direct / hd60/load2 | original | 1 / 9 | — | — | Insufficient | — | No |
| direct / hd60/load2 | stock | 1 / 9 | — | — | Insufficient | — | No |
| direct / raw30/load0 | original | 3 / 9 | 2.3782 | 2.4107 | -1.654% | 0.980260–0.986062 | No |
| direct / raw30/load0 | stock | 3 / 9 | 2.3782 | 2.4121 | -1.801% | 0.978012–0.984411 | No |
| direct / raw30/load2 | original | 7 / 9 | 2.3285 | 2.3743 | -2.033% | 0.977730–0.981932 | No |
| direct / raw30/load2 | stock | 7 / 9 | 2.3285 | 2.3755 | -1.994% | 0.977327–0.982943 | No |
| workflow / hd60/load0 | original | 9 / 9 | 5.6018 | 5.6954 | -1.764% | 0.979057–0.985468 | Yes, bounded |
| workflow / hd60/load0 | stock | 9 / 9 | 5.6018 | 5.7016 | -1.743% | 0.979896–0.985302 | Yes, bounded |
| workflow / hd60/load2 | original | 9 / 9 | 5.6307 | 5.7251 | -1.532% | 0.982220–0.987248 | Yes, bounded |
| workflow / hd60/load2 | stock | 9 / 9 | 5.6307 | 5.7376 | -1.791% | 0.979719–0.984871 | Yes, bounded |

Complete HD workflow passed its two bounded groups. Direct HD accepted only 1/9 each, raw 3/9 and 7/9. **Overall performance/promotion gate failed. Original native 0.6.0 was retained.** A small raw interval below 1 does not override the preregistered sample requirement.

## Workload and controls

- Apple M4 Max, 10P + 4E, 36 GiB, macOS 27.2.
- Big Buck Bunny 1920×1080 at 30fps; HD 60–120s, raw YUV420p 60–90s (2,799,360,000 bytes).
- Matched libx264 veryfast/CRF20, encoder/decoder/filter 8/2/2, workflow validation 8, HD AAC160k.
- load0 has no added owned CPU helper; load2 has two 50%-duty helpers. Other host activity is observed/gated, not absent.
- Warm cache and temporary input/runtime residency checks; parent-side child-lifetime timers and actual counters. No fixed CPU affinity, frequency or thermal state.
- Direct: 688 completed cases including 12 excluded warmups, 180 attempted blocks. Workflow: 144 including 6 excluded warmups, 23 attempted blocks.
- Rejected blocks remain in the evidence; they are excluded from accepted timing. No pooling of warmups, interrupted runs or different epochs.
- The original lab used an explicit task-scoped system-memory waiver, nice≥10, 12 GiB owned-job cap, disk/mount/output/deadline guards.

## Quality and compression

| Source | VMAF mean | PSNR-Y dB | SSIM | Metric delta vs both references |
|---|---:|---:|---:|---:|
| hd60 | 94.781527 | 47.011742 | 0.998632 | 0 |
| raw30 | 94.920178 | 46.621946 | 0.998291 | 0 |

Strict full-frame decoded video identity and HD audio identity passed on the target outputs. Fresh native media/CLI/MCP checks (14) and six codec-mode checks passed. Scheduling-dependent codec modes had strict decode/assertion acceptance rather than an exact-byte equivalence claim. Private container files differ by 14 metadata bytes; this is not a compression-ratio improvement.

## CPU work and remaining acceptance

Descriptive instruction counts decreased approximately 4.46–4.85% versus original native and 4.78–5.25% versus Stock across completed cases. Those counts include invalid-environment blocks and are **not** elapsed-time acceptance. Phase 10 reduced progress-query lock traffic about 98.4%; its wall-clock gate still failed.

Remaining gaps: enough stable whole blocks in every direct workload/load, independent wider-source/hardware confirmation, and fresh new-prefix FATE/native/extended/GPU/fault/soak/consumer/install-update-rollback acceptance. Old receipts cannot accept a new engine.

## Earlier epochs and reproduction

Phase 8 reduced complete-workflow time 22.31% (BBB) and 30.77% (ToS) against the old native workflow with different concurrency. Its same-tuning Stock comparison still included HD slowdowns; see the full report. Phase 9 lookahead calibration failed independent confirmation (39.94% slower), and Phase 10 instruction improvements did not pass elapsed-time confidence. These are distinct experiments, not one pooled speedup.

Use [all reports](REPORTS.md), [Phase 11 method](PHASE11-RESEARCH.md), [full Phase 11 report](PHASE11-RESULTS.md), [summary JSON](benchmarks/phase11-summary.json), [direct analysis](benchmarks/phase11-direct-analysis.json) and [workflow analysis](benchmarks/phase11-workflow-analysis.json). Analyses retain exact block ratios and original source-report hashes; private paths are redacted. Raw corpus/profiles/full process receipts are not bundled. The scripts are auditable research recipes, not a turnkey reproduction without those inputs.

For a new local bounded test, first review `ffv2 benchmark-plan INPUT --output-dir DIR`; that command is separate from the preregistered historical Phase 11 experiment. Publish full quality, failures, environment and uncertainty with any new result.
