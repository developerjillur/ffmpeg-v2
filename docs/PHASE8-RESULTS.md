# Phase 8 — HD ও live-action software performance

Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬। Final local release **0.6.0**, frozen pair **0.6.0-fc5c8de8ba2a58f7** installed ও verified। Performance functional candidate **0.6.0rc1**-এ মাপা; final-এ শুধু দুই version literal বদলেছে। Matching final regression, installed output ও version bridge retained।

## মাপা ফল

একই real publisher source-এর 60–120s range, একই native engine, x264 `veryfast / CRF 20`, AAC 160k এবং complete validation contract। প্রতি source/configuration একটি excluded warmup ও **৯টি নতুন measured trial**। Calibration-এর তিন trial এই confirmation-এ ব্যবহার হয়নি। আট configuration/source group-এ মোট 80 actual jobs; 72 measured। Slow trial-ও retained।

সব comparator একই typed workflow চালিয়েছে: capability lookup → probe/plan → durable queue → encode → metadata check → complete strict decode → SHA-256 → atomic publish। নিচের সময় `total_seconds`-এর median; fresh interpreter startup এর বাইরে। এটি একই safeguards-সহ Stock engine-এর তুলনা।

Captured binary-binding environment Darwin **27.2.0 / arm64**; end audit-এ live macOS **27.2**, default `python3` **3.9.6** (`/Library/Developer/CommandLineTools/usr/bin/python3`)। Native `n9.0.2-3-gb6e0de6-ffmpeg-v2-m4`, Stock Homebrew **9.0.2**। Saved exact argv, source hashes, SDK hashes, binary/dependency bindings ও resource traces retained। Same actual source/operation-এর workload একই; driver নিজে niceness অন্তত 10 রাখে।

| 60s workload | 0.5.0 Native, 4/2/2/4 | Stock, আগের 4/2/2/4 | নতুন Native, 8/2/2/8 | Stock, একই নতুন 8/2/2/8 | পুরোনো Native থেকে সময় কম | আগের Stock থেকে সময় কম |
|---|---:|---:|---:|---:|---:|---:|
| BBB 1920×1080 / 30fps | 9.6969s | 9.7344s | **7.5339s** | 6.8781s | **22.31%** | **22.61%** |
| Tears of Steel 1920×800 / 24fps | 7.7771s | 7.5278s | **5.3840s** | 5.4297s | **30.77%** | **28.48%** |

ToS live-action/VFX source-এর actual height 800। একই epoch-এর baseline ও candidate তুলনা করা হয়েছে; আগের report-এর আলাদা দিনের সময় দিয়ে percentage গণনা হয়নি।

Fresh benchmark-case process wall median, Python startup-সহ: HD পুরোনো Native **9.7812s**, আগের Stock **9.8451s**, নতুন Native **7.6224s**, matched Stock **6.9464s**। ToS যথাক্রমে **7.8700 / 7.6300 / 5.4625 / 5.5460s**। এগুলো case-process measurements; installed CLI output-identity proof পৃথক gate।

Ratio of medians-এর 20,000 paired trial-block bootstrap draws; 95% interval নিচে। Ratio<1 হলে candidate দ্রুত।

| Workload / তুলনা | সময়ের ratio | 95% interval | ফল |
|---|---:|---:|---|
| HD / পুরোনো Native | 0.776939 | 0.628577–0.957856 | ঘোষিত speed gate pass |
| HD / আগের Stock preset | 0.773946 | 0.577062–0.879356 | ঘোষিত speed gate pass |
| HD / একই নতুন Stock tuning | 1.095348 | 0.979218–1.315438 | Median 9.53% ধীর; interval equality পার করে |
| ToS / পুরোনো Native | 0.692296 | 0.626809–0.747001 | ঘোষিত speed gate pass |
| ToS / আগের Stock preset | 0.715217 | 0.670815–0.765480 | ঘোষিত speed gate pass |
| ToS / একই নতুন Stock tuning | 0.991582 | 0.625907–1.070255 | Median 0.84% দ্রুত; interval equality পার করে |

**একই নতুন tuning-এ native core সর্বদা Stock-এর চেয়ে দ্রুত—এমন প্রমাণ নেই।** HD-এর নতুন matched-control median gap report-এ retained। নতুন workflow পুরোনো Native এবং পুরোনো Stock preset-কে ছাড়িয়েছে; Stock-এ একই tuning প্রয়োগ করলেও লাভ হয়। Native C compression algorithm বা x264 library বদলানো হয়নি। Busy host, serial workload order ও ছোট sample সংখ্যা uncertainty-এর সীমা; sampled waits বা interval দিয়ে নির্দিষ্ট OS scheduling cause নিশ্চিত করা যায় না।

## কোন stage উন্নত হয়েছে

| Stage median | HD পুরোনো → নতুন Native | ToS পুরোনো → নতুন Native |
|---|---:|---:|
| Encoding | 7.729290 → 6.241100s | 6.165230 → 4.281684s |
| Full decode / validation | 1.520726 → 1.010006s | 1.401187 → 0.840073s |
| Planning/probe | 0.043235 → 0.046880s | 0.039994 → 0.041591s |
| Capability lookup | 0.002371 → 0.002512s | 0.002414 → 0.002644s |

প্রতিটি stage-এর median আলাদাভাবে নেওয়া; এদের যোগফল total median হওয়ার কথা নয়। মূল লাভ codec concurrency ও validation-এ; capability lookup-এ নতুন speed claim নেই।

আগের API encoder/validation pool সর্বোচ্চ ৪-এ আটকে ছিল। HD-এর পুরোনো nominal codec/filter/audio budget ৯; নতুনটি ১৩, অনুমোদিত ১৪-এর মধ্যে। Validation আলাদা phase। Actual OS/library/lookahead/guardian thread count এই arithmetic দিয়ে capped নয়। Native/Stock একই verified x264 library নেয় এবং native-এ `-O3`, M4 target ও actual NEON path আছে। চার owned warmup CPU sample measured timing থেকে বাদ। [সম্পূর্ণ অনুসন্ধান](PHASE8-RESEARCH.md)।

HD matched-control gap খতিয়ে দেখতে আরও **48টি adjacent stage run** হয়েছে: 30s/900-frame identical decoded reference, চার stage, পাঁচ measured pair এবং excluded warmups। Native decode/filter 4.25% দ্রুত; compressed video-only ratio 0.9955 এবং audio/video encode ratio 1.0119, উভয়ের interval equality পার করে। Compressed-path test একটি stable 9.5% defect পুনরাবৃত্ত করেনি। Raw-reference x264 feed-এ native 4.44% ধীর (95% 1.0012–1.1074), যা raw I/O/feed control-এর সীমিত unresolved difference; production compressed workflow-এর result-এর বিকল্প নয়। [Stage table ও সীমা](PHASE8-RESEARCH.md#confirmation-এর-hd-gap-এর-পরের-isolation)।

## Quality ও compression

প্রতি output-এর **সব 1,800 HD / 1,440 ToS frames** source-এর একই decoded frame number-এর সঙ্গে aligned। Metric reuse কেবল output SHA, source SHA, range, fps, frame count ও metric-file contents মিলে হয়েছে। Confirmation-এর সব configuration-এ output deterministic; Native ও Stock একই pools-এ byte-identical।

| Workload | VMAF পুরোনো → নতুন | ΔPSNR-Y | ΔSSIM | File bytes পুরোনো → নতুন | Size পরিবর্তন |
|---|---:|---:|---:|---:|---:|
| HD | 94.761184 → 94.781527 | +0.004890dB | +0.000001 | 20,305,248 → 20,338,056 | +0.161574% |
| ToS | 93.375096 → 93.379144 | +0.000316dB | +0.000002 | 21,373,455 → 21,378,650 | +0.024306% |

আগে ঘোষিত gates: ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05dB, ΔSSIM≥−0.00001, size≤1.02×। সব pass। এই সামান্য metric difference-কে বড় perceptual improvement বলা হয়নি। সময় কমাতে bitrate/quality নামানো হয়নি; file কিছুটা বড় হয়েছে। Audio stream, duration, dimensions, frame count, strict full decode, SHA ও validated publish বহাল।

## Default ও API

`m4_max_hd_software` কেবল matching M4 Max, ≥60s, 1920-wide native geometry/height≤1080, progressive square pixels, unrotated 8-bit 4:2:0 H.264/VP8, metadata-matched explicit native integer fps≤30, software decode/filter এবং quality mode-এ 8/2/2/8 নেয়। Caller pool overrides, bitrate, checkpoint, HDR/deinterlace, resize/UHD ও অন্য CPU এই নতুন profile নেয় না। পুরোনো profile/conservative behaviour retained।

Explicit software transcode encoder/validation সর্বোচ্চ ৮; decoder/filter সর্বোচ্চ ৪ এবং nominal total encode budget ১৪। Hardware/অন্য operation-এ বড় encoder pool ও over-budget requests refused। [Software HD example](../examples/transcode-software-hd.json), [CLI operations](OPERATIONS.md), [MCP contract](MCP.md)।

## Release ও regression evidence

সব ছয়টি Phase 8 requirement completed। [Portable evidence index](verification/phase8-2026-11-04.json) exact paths/checksums, comparisons, memory, versions ও retained gates দেয়; [register](../PHASE8.md) প্রতিটি requested outcome ধরে।

| Gate | Actual result |
|---|---|
| Final source regression | Python 3.9.6 ও 3.14.7-এ **131টি করে test**; default-policy tests থেকে task waiver removed |
| Calibration | সাত configuration × দুই source × warmup+তিন trial = **56 complete jobs** |
| Independent confirmation | **80 complete jobs**, 72 measured; actual full-decode progress মোট **129,600 frames** |
| Extra stage isolation | চার stage × দুই engine × warmup+পাঁচ trial = **48 supervised stages**; 900 identical reference frames |
| Advanced workflows | **17** actual concat/subtitle/audio/image/HDR/error cases |
| Checkpoint ও failures | **8** interruption/corruption/preemption/publish/write-denial/worker/supervisor/both-loss/cancel/timeout cases |
| CLI defaults | Source ও installed launcher-এ চারটি করে actual long export; HD/ToS নতুন এবং UHD/resize আগের quality-approved SHA-এর সঙ্গে byte-identical |
| MCP | Source RC এবং configured installed final **0.6.0** fresh connection; queue/replay/priority/PCM/mix/cancel/path/schema, actual 8-thread/12-frame encode, hardware/over-budget refusal |
| Existing Studio | Source এবং installed exec-এ তিনটি করে export/retained-part recovery/tamper-refusal checks; existing scripts ও reused assets unchanged |
| Release lifecycle | **10** actual cases: RC install, queued/running fence, tampered acceptance, stale installed/source client, cross-release refusal, rollback checkpoint reuse/3,600-frame output, prior stable run ও final reactivation |
| Installed pair | **45 package files + 38 native/non-system library files** cold verified; same Stock dependency closure ও per-comparator binding identity verified |
| Client configuration | Existing entry-এর read-only check; before/after byte hash একই, নতুন version-এর generic setup helper, অন্য settings unchanged |

Frozen **0.5.0** performance experiment চলাকালীন অপরিবর্তিত ছিল। Final default rollback target **0.5.0-16f948bf021bd8b7**; RC এবং successful checkpoints-ও retained। নতুন native C algorithm/build/FATE run হয়নি। আগের native base 14/extended 21, local FATE 2,893 ও selected external 15, formats এবং elapsed soak gate তাদের original receipt ও unchanged engine identity দিয়ে reuse হয়েছে।

Calibration-এর exact 35 SDK file bytes retained RC snapshot এবং frozen baseline-এর `tuning.py` থেকে পুনর্গঠন করে checksum মিলেছে; recipe receipt `<LAB_ROOT>/ffmpeg-v2-phase8/calibration-source-reconstruction.json`। Confirmation-এর auto-profile implementation আলাদা exact hashes-এ measured। Local source checkpoint/tag **v0.6.0**; public push/deployment হয়নি।

Deliberate worker/both-kill drill-এর দুই stale `running` ledger record standard `Store.recover` ও shared host lock-এর মধ্যে `interrupted` হয়েছে। নতুন encode/retry/publish শুরু হয়নি; partials ও original diagnostics retained। অতিরিক্ত receipt `<LAB_ROOT>/ffmpeg-v2-phase8/fault-ledger-recovery.json`। Post-commit audit default ও owned task databases-এ active jobs শূন্য এবং clean matching tag যাচাই করে।

## Resource tradeoff

| Native workflow | পুরোনো sampled job peak-এর median | নতুন sampled job peak-এর median | নতুন সর্বোচ্চ sampled peak |
|---|---:|---:|---:|
| HD | 329.06MiB | 396.58MiB | 397.78MiB |
| ToS | 246.44MiB | 301.00MiB | 301.36MiB |

বেশি concurrency কিছু বেশি memory নেয়। এই মান owned process tree-এর sampled footprint; পুরো computer বা instantaneous peak নয়। Scratch directory মেপে **5.97GiB** পাওয়া গেছে, raw reference-সহ; useful outputs/failed attempts/logs retained। Native core rebuild, বড় download বা source media duplicate করা হয়নি। Studio ও MCP-এর ছোট integration artifacts তাদের প্রয়োজনীয় approved project paths-এ আছে।

## Scope ও সীমা

এই ফল দুই retained publisher source, এক M4 Max এবং নির্দিষ্ট software quality preset-এর। 4K/resize-এর quality-approved output identity regression আলাদা; নতুন HD percentages সেগুলোতে প্রযোজ্য নয়। Full external FATE, overnight reliability, arbitrary camera/HDR, other codecs/CPUs, perceptual mastering ও reproducible public distribution নতুন করে accepted হয়নি। আগের binary/FATE/format/30-minute soak receipts তাদের নিজস্ব original paths ও scope-এ retained।

Scoped task memory waiver ব্যবহৃত হয়েছে। Sampled 12GiB job-footprint, disk/mount/deadline/output checks বহাল। Heavy work sequential; new scratch data mounted `<LAB_ROOT>/ffmpeg-v2-phase8`-এ। নতুন x264/native dependency download, unsafe floating-point build, source asset replacement বা unrelated application shutdown হয়নি।
