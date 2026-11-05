# Phase 11 — conditioned replay, private PGO এবং acceptance ফল

Maintainer: **Jillur Rahman**। 2026-11-05 (Asia/Dhaka)।

**Default release:** `0.6.0-e07af57a8214502f`। নতুন candidate quality-verified experimental; required wall-clock gates একসঙ্গে pass হয়নি, তাই promote করা হয়নি।

Workload: BBB1920×1080/30fps-এর60–120s HD এবং60–90s raw YUV420p; raw file2,799,360,000bytes। Matched libx264/veryfast/CRF20, encoder8/decoder2/filter2; complete workflow validation8 এবং HD audio AAC160k। Progress contract matched। This machine/source/range ও admitted warm-cache conditions পর্যন্ত ফল প্রযোজ্য।

## পরিবর্তন ও quality

M4/vectorized private x264-এ disjoint training দিয়ে PGO; LTO নেই, safety assertions retained। Parent-side kernel start/exit clock এবং per-core CPU counter; একই input ও native runtime images bounded temporary lock করে residency যাচাই। Original/Homebrew ও installed code/native content unchanged; mount metadata recovery supplements-এ আলাদা।

HD1800video+2813audio এবং raw900video frame-এর fresh strict decoded timestamps/size/SHA256 exact match। Encoded private output আগের quality output-এর সঙ্গে exact SHA; VMAF/PSNR-Y/SSIM delta0। Private metadata-এর কারণে14bytes container difference।

| Source | VMAF mean | PSNR-Y dB | SSIM mean | Candidate delta vs Stock/Native |
|---|---:|---:|---:|---|
| hd60 | 94.781527 | 47.011742 | 0.998632 | 0 / 0 / 0 |
| raw30 | 94.920178 | 46.621946 | 0.998291 | 0 / 0 / 0 |

## Independent direct timing

Completed cases 688; excluded warmups 12; attempted blocks 180। প্রতি workload/load-এ9 accepted blocks প্রয়োজন।

load0=অতিরিক্ত নিজস্ব CPU worker নেই; load2=দুটি50%-duty controlled CPU worker। Other host activity observed ও gated; CPU affinity/frequency/thermal state fixed নয়।

| Workload/load | Valid blocks | Reference | Candidate s | Reference s | Paired time change | Ratio95% CI |
|---|---:|---|---:|---:|---:|---|
| hd60/load0 | 1 | Native/Stock | — | — | অপর্যাপ্ত stable blocks | — |
| hd60/load2 | 1 | Native/Stock | — | — | অপর্যাপ্ত stable blocks | — |
| raw30/load0 | 3 | original | 2.3782 | 2.4107 | -1.654% | 0.9803–0.9861 |
| raw30/load0 | 3 | stock | 2.3782 | 2.4121 | -1.801% | 0.9780–0.9844 |
| raw30/load2 | 7 | original | 2.3285 | 2.3743 | -2.033% | 0.9777–0.9819 |
| raw30/load2 | 7 | stock | 2.3285 | 2.3755 | -1.994% | 0.9773–0.9829 |

Displayed seconds accepted-case medians; time change হলো paired block ratios-এর geometric mean, displayed medians-এর ratio নয়। Negative change মানে কম elapsed time। CI equality অতিক্রম করলে কিংবা9 stable blocks না হলে speedup proven নয়।

## Complete typed HD workflow

| Workload/load | Valid blocks | Reference | Candidate s | Reference s | Paired time change | Ratio95% CI |
|---|---:|---|---:|---:|---:|---|
| hd60/load0 | 9 | original | 5.6018 | 5.6954 | -1.764% | 0.9791–0.9855 |
| hd60/load0 | 9 | stock | 5.6018 | 5.7016 | -1.743% | 0.9799–0.9853 |
| hd60/load2 | 9 | original | 5.6307 | 5.7251 | -1.532% | 0.9822–0.9872 |
| hd60/load2 | 9 | stock | 5.6307 | 5.7376 | -1.791% | 0.9797–0.9849 |

এই complete workflow-এর ফল এই HD source/range ও warm-cache conditions-এর জন্য। দুই load-এ9 valid blocks/18 cases per engine; অন্য source বা encoder-only gap বন্ধ হওয়ার দাবি নয়। Overall release gate এখনও direct sample insufficiency-তে fail।

একই SDK/8-2-2-8 pools, matched progress, planning/encode/full decode/hash/no-clobber publish। Live root-only counters-কে descendant counters বলা হয়নি।

## CPU work — descriptive

| Workload/load | Completed counts Native/PGO/Stock | Instructions vs Native | Instructions vs Stock |
|---|---|---:|---:|
| hd60/load0 | 43/45/41 | -4.458% | -5.233% |
| hd60/load2 | 53/51/46 | -4.475% | -5.249% |
| raw30/load0 | 60/64/64 | -4.810% | -4.777% |
| raw30/load2 | 67/71/71 | -4.846% | -4.810% |

এই CPU-work table-এ invalid-environment block-এর completed case-ও আছে; এটি wall-clock acceptance proof নয়।

## Verification ও বাকি gap

- Native media/CLI/MCP14 checks এবং6 codec modes pass; deterministic8/10-bit, references/B-frames, slices, single-thread ও interlaced exact decode comparison। Scheduling-dependent mode-এ strict decode/assertions pass; exact equivalence claim নেই।
- দুই Python runtime-এ 176/176 tests pass; default memory policy tests task waiver ছাড়া।
- Owned databases 35, active jobs0। Baseline installed package/engine pair cold hash verified।
- Remaining gap: whole-block CPU/P-share stability ও per-workload wall-clock confidence gate। Instruction reduction-কে speedup বলা হয়নি। New-prefix FATE/soak/install/rollback promotion lifecycle চালানো হয়নি, কারণ performance acceptance হয়নি।

সব completed/failed/rejected artifacts retained; cache warmup cost এবং rejected reasons raw evidence-এ আছে। Detailed method `docs/PHASE11-RESEARCH.md`; cold index `<PROJECT>/docs/verification/phase11-2026-11-05.json`; external work root `<LAB_ROOT>/ffmpeg-v2-phase11`।

## Original release recovery

Current original0.6 package/native content unchanged; stale device bindings fresh verification দিয়ে পুনরুদ্ধার। Retained0.5-ও exact old package ও same verified original native content-এ rebound; actual rollback এবং installed CLI/MCP checks-এর পরে0.6-এ ফেরত। এটি PGO promotion lifecycle নয়।
Verified fallback: `0.5.0-018d61f631128c48`। Old snapshots/proofs retained।

Supplement: `<LAB_ROOT>/ffmpeg-v2-phase11/mount-recovery-20261104T153507/report.json` (SHA256 `4844ba547ec9136cc69b0f347ad0c3b5f565d3d0c8a0a21ee7f43bfdfeac60bb`)।
Supplement: `<LAB_ROOT>/ffmpeg-v2-phase11/mount-recovery-20261104T153507/rollback-recovery.json` (SHA256 `8b36238cd04c52d7276e2316b7689785a836cc33d96ebd18cada3f332bac207a`)।