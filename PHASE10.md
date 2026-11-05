# Phase 10 — controlled CPU-load replay ও worker profiling

Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬। Frozen source `bf96b96b099afea0d0326c9852d20e2a135572b9`; active verified release `0.6.0-fc5c8de8ba2a58f7`। Phase 9-এর rejected queue/lookahead defaults বহাল হবে না।

- [x] একই inputs/argv/native ও Stock dependency hashes freeze; resource/mount/queue snapshot retained।
- [x] Bounded owned CPU load replay: 180 encodes, 7 balanced blocks, 168 measured / 12 warmups। Residual host CPU ও actual synthetic duty measured; no-added-load-কে idle বলা হয়নি।
- [x] Calibrated per-worker CPU/mutex/condition ও process runnable/P-core/page-wait/disk counters। Per-engine V5 observer binding verified; process-only observer-এ pthread hooks বাদ। সব profiling speed acceptance থেকে excluded।
- [x] Actual x264 atomic progress ও acquired lower-bound cache implement; original Homebrew অক্ষুণ্ণ। Same source generic base, atomic-only, M4, LTO ও final vectorized/no-LTO variants পৃথক। LTO crash rejected।
- [x] Independent HD/raw quality ও timing; 45 full HD workflows, strict decode/hash/publication। 1,800 HD video / 2,813 audio / 900 raw decoded frame SHA-256 exact match; metric deltas 0।
- [x] দুই runtime-এ 142 tests, native CLI/MCP/media 14 checks, ছয় codec-mode regressions ও actual 8/10-bit negative-publication TSAN। Cold audit: 37 databases, active jobs 0; source/native/library hashes verified।
- [ ] Stable wall-clock Native improvement ও Stock gap closure: predeclared confidence gates **pass হয়নি**। কম instructions বা ভালো median দিয়ে gate replace করা হয়নি।
- [ ] Default release promotion: candidate **verified experimental, not activated**; installed `0.6.0-fc5c8de8ba2a58f7` retained। নতুন stable acceptance ছাড়া release lifecycle শুরু হয়নি।

প্রমাণিত source/target efficiency: active Native-এর তুলনায় 2.9–3.3% কম instructions, bounded captured x264 mutex traffic প্রায় 98.4% কম। Exact পুরোনো slowdown-এর causal percentage নির্ধারিত নয়; ready queue এবং raw file-cache imbalance measured contributors। [সম্পূর্ণ ফল](docs/PHASE10-RESULTS.md), [method](docs/PHASE10-RESEARCH.md), [cold evidence](docs/verification/phase10-2026-11-04.json), [patches](third_party/x264/README.md)।

Quality gates: ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05dB, ΔSSIM≥−0.00001, size≤1.02×। Exact encoded SHA হলে same source/range/fps/model-এর prior full-frame metrics reuse করা যায়। Native improvement-এর জন্য faster median ও independent paired whole-block 95% upper ratio<1 প্রয়োজন। Stock gap closed-এর জন্য median ratio≤1 ও upper≤1.02 প্রয়োজন। Calibration, profiling ও confirmation পৃথক; সব measured slow run retained।

Work root `<LAB_ROOT>/ffmpeg-v2-phase10`; mounted volume checked। Existing 2.61GiB raw reused; initial scratch estimate ≤6GiB, media/profiler job estimate 2GiB, own synthetic load ≤2 workers/≤64MiB total; actual process CPU duty measured। Heavy jobs sequential, niceness≥10, memory/disk/deadline/output guards retained। আগের explicit owner system-memory waiver শুধু task invocation-এ; production policy অপরিবর্তিত। Sampled total job hard limit 12GiB, boot disk <400GB ও ≥15GiB free। Initial boot use 390.06GB; নতুন media/build/cache সব external work root-এ। অন্য apps/services বন্ধ বা priority পরিবর্তন করা হবে না।

`xctrace` unavailable; local SDK ও public Darwin APIs দিয়ে bounded diagnostic observer। Kernel counter units SDK/XNU source ও calibration দিয়ে verify না করে CPU wait শতাংশ বলা হবে না। Unmeasured residual wall time-কে runnable wait বলা যাবে না।
