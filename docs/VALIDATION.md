# Local verification — ৪ নভেম্বর ২০২৬

Current release **0.6.0**, installed frozen pair **0.6.0-fc5c8de8ba2a58f7**। Native core `n9.0.2-3-gb6e0de6-ffmpeg-v2-m4` ও 38 bindings একই; C source head `b6e0de6…`। Stable 0.5.0 default rollback target। [Phase 8 comparison](PHASE8-RESULTS.md), [portable proof](verification/phase8-2026-11-04.json), [register](../PHASE8.md)।

Phase 8-এর final Python 3.9.6/3.14.7-এ **131 tests করে**, calibration 56 complete jobs, independent confirmation 80 jobs/72 measured, all-frame HD 1,800 ও ToS 1,440 quality/size gate pass। পুরোনো Native-এর তুলনায় সময় 22.31%/30.77% কম; আগের Stock preset থেকে 22.61%/28.48% কম। একই নতুন Stock control-এর intervals equality পার করে; raw-feed gap retained।

Fresh advanced 17, checkpoint/fault 8, actual lifecycle 10, source/installed typed MCP-এর eight-thread encode এবং default CLI/Studio integration-এর পৃথক receipts আছে। Existing client configuration byte-identical। RC→final-এ শুধু দুই version literal বদলেছে; matching fresh final regression ও bridge retained। নিচের broader binary/FATE/soak/format ফল 0.5.0-এর historical acceptance; Phase 8-এ নতুন run হিসেবে দেখানো হয়নি।

## সংরক্ষিত Phase 4–7 — 0.5.0

তৎকালীন frozen pair `0.5.0-16f948bf021bd8b7`। [Comparison](PHASE4-7-RESULTS.md), [index](verification/phase4-7-2026-11-03.json), [register](../PHASE4-7.md)।

| Gate | Actual ফল |
|---|---|
| Final source controls | দুই Python runtime-এ 126 tests করে; default-policy controls task waiver থেকে isolated |
| Native base/extended | 14 + 21 checks; current library identities-তে matrix, 38 runtime files |
| Long performance | 12 excluded warmup + 60 measured outputs, পাঁচ paired trial; চার speed/quality/size gate pass |
| Advanced workflows | 17 concat/subtitle/mix/image/HDR positive/error checks; independent packet/PTS/PCM/pixel proof |
| Checkpoint/failures | 8 actual cases; corruption/reuse/preemption, owned worker/supervisor/both-loss, cancel/timeout/write denial ও publish recovery |
| Long batch/soak | তিন real 180s export = 15,120 frames; actual 30-minute soak = 54,000 frames, 355 sampled records |
| Formats/FATE | 15 format cases; 2,893 local records/zero failures; 15 selected external targets, full 5,554-target suite নয় |
| Release lifecycle | 9 cases; update fences, bad candidate, stale installed/source MCP, cross-code refusal, rollback checkpoint recovery ও final reactivation |
| Installed front doors | Configured 0.5.0 MCP PCM/mix/replay/priority/refusals; চার default CLI output same SHA; installed exec→actual Studio export/recovery/tamper |
| Integrity | Source/output hashes, full strict decode, frozen code/engine snapshots, no-clobber publish; originals ও diagnostics retained |

v0.4 workflow থেকে চার median সময় 17.75%, 16.91%, 14.53%, 24.31% কম। Same tuned native/Stock files-এর bytes সমান; native/Stock-এর চার interval-ই equality পার করে। Size পরিবর্তন −0.015% থেকে +0.005%। RC→final-এ শুধু দুই version literal বদলেছে; bridge ও fresh final regression আছে।

Metadata-বিহীন publisher HDR sample refuse হয়েছে; positive HDR proof analytic। Studio acceptance technical; creative approval নয়। 30-minute soak overnight/kernel guarantee নয়। Configured fresh connection verified; current chat hot reload আলাদা। Default resource policy অপরিবর্তিত; task waiver scoped। [Limits](READINESS.md)।

## সংরক্ষিত Phase 3 — 0.4.0

তৎকালীন release **0.4.0**। Native core n9.0.2-3-gb6e0de6-ffmpeg-v2-m4 অপরিবর্তিত ও active। **102 control tests** Python 3.9.6/3.14.7-এ এবং **32 actual acceptance checks** pass: 14 native, 12 media/GPU/error, 3 existing fault drills, MCP priority ও 2 নতুন scaling/supervisor-loss checks। Active 30 files-এর hashes আবার মিলেছে। Native C বদলায়নি; Phase 2-এর 2,893 local FATE records/zero failures historical acceptance reuse হয়েছে, নতুন FATE run দাবি নেই।

Phase 3-এর full tables, paired timing uncertainty, unchanged output, cache/priority/recovery এবং hardware scaling-এর negative result [Phase 3 report](PHASE3-RESULTS.md)-এ। Portable proof [verification/phase3-2026-11-03.json](verification/phase3-2026-11-03.json)। Same-engine native pipeline −21.44%, actual CLI process −17.75%; final stock/native pipeline +3.31%, পৃথক CLI −3.41%, দুটির interval equality পার করে। অতিরিক্ত compression 0%। HDR correction, GPU C fix, natural corpus, sparse sampling ও real-time soak-এর [Phase 2 report](PHASE2-RESULTS.md) এবং [proof](verification/phase2-2026-11-03.json) সংরক্ষিত।

## সংরক্ষিত Phase 1 baseline — ২ নভেম্বর ২০২৬

নিচের অংশ historical release **0.2.0**-এর ফল। Maintainer: **Jillur Rahman**। Machine Apple M4 Max, Mac16,9, 36 GiB, 10P+4E। Generated local fixtures; কোনো client corpus প্রকাশ করা হয়নি।

Machine-readable sanitized ফল [verification/2026-11-02.json](verification/2026-11-02.json)-এ। Raw logs, outputs ও attempts project-private .runtime/verification-এ; core build data mounted NexaWork-এ।

## ফল

| পরীক্ষা | Observed |
| --- | --- |
| Control/regression | 70 pass; Python 3.9.6 এবং 3.14.7 |
| Core | n9.0.2-1-g3f0d329-ffmpeg-v2-m4; clang 21; --cpu=apple-m4 |
| Local FATE | Successful make fate, 2,691 result records, 0 failure; 2,692 listed targets-এর hwdevice default run-এ record নয় |
| Progress | Native JSONL schema, legacy kv, invalid format rejection; actual encode receipt-এ JSONL consumed |
| Audio | 440Hz nonzero RMS≈2895.706, 16kHz output; পৃথক sine/impulse PCM bit-exact |
| A/V export | Software ও actual no-software-fallback VideoToolbox H.264/AAC; full decode/hash/publish |
| Frame/sheet | Requested/actual source PTS; 16 samples, individual/batch timestamps equal |
| Remux | H.264/AAC packet hashes equal, 120 video/189 audio packets; Main10 remux bit depth/colour metadata retained |
| Larger path | 3840×2160 HEVC Main10 hardware encode, hardware download as p010le, full decode, 1080p H.264 export |
| Long timeline | 600.0s, 18,000 video frames; audio/video end 600.0s; full decode; 64,110,785 bytes |
| CLI/MCP | Real handshake→queue/replay→worker→status→output hash/PCM; cancel/refusal; global native launchers |
| Engine | 28 binary/non-system dependency files hashed; resolved load paths protected; reversible selection |

A/V endpoints সমান পাওয়া perceptual lip-sync বা 600s wall-clock soak প্রমাণ করে না। Full external-sample FATE বা every hardware target চালানো হয়নি।

## Repeated timing

একটি 6s, 1280×720/30fps FFV1/PCM fixture, 3 trial, fixed shuffled order, sequential jobs, 2 codec threads। Software preset veryfast, 4Mbps H.264 target; hardware একই target। No warmup exclusion। Encode এবং validation timing আলাদা।

| Encoder | Installed encode median | M4 fork encode median |
| --- | ---: | ---: |
| libx264 | 0.512835s | 0.484191s |
| h264_videotoolbox | 0.717588s | 0.490727s |

Busy-host variation/outlier ছিল। এই comparison general বা M4 flags-এর causal speedup প্রতিষ্ঠা করে না। একই prebuilt external codec libraries ব্যবহৃত হয়।

Frame workflow: individual median 11.554122625s, batch median 0.818768833s, ratio **14.1115809×**। 16 targets-এর source PTS একই। Baseline-এর mosaic assembly বাদ ছিল; নতুন workflow sheet তৈরি করে। Dense-window result; long sparse ranges-এ অন্য ফল হতে পারে।

## Quality alignment

প্রথম metric pass Matroska millisecond timestamps ও MP4 rational timestamps দিয়ে 181 framesync samples নিয়েছিল; সেটি superseded। Existing encode outputs পুনর্ব্যবহার করে decoded frame number at 30fps-এ ঠিক 180 frames align করা হয়েছে। নতুন score:

| Encoder | Installed VMAF / SSIM | Native VMAF / SSIM |
| --- | --- | --- |
| Software | 97.521175 / 0.999420 | 97.521175 / 0.999420 |
| VideoToolbox | 96.056957 / 0.998627 | 96.056957 / 0.998627 |

Software-এর 6 whole-file SHA-256 একই। Hardware output file hashes varied; প্রথম matched sample-এর measured quality একই। Software বনাম hardware-এর quality এক নয়। Metrics-এর reference [official libvmaf filter](https://ffmpeg.org/ffmpeg-filters.html#libvmaf)।

## Evidence directories

- Core successful build job be7d81f383d944dc9ba5ac24e86c8fd0, original state .runtime/verification/m4-owner-20261102T141129-a936b0d8/state।
- Native media native-media-20261102T145430-8243c3c4।
- Benchmark benchmark-native-20261102T145507-9e28a965; corrected quality quality-aligned-report-286ae76e.json।
- Larger matrix large-media-20261102T145846-87377acc।
- MCP mcp-pipeline-20261102T150418-aaaa2c8f।
- Active CLI/PCM 20261102T150809-b34b9dec; auto-release-state actual software selection/JSONL।

Failed attempts রাখা হয়েছে: default/serial preflight refusal (পুরোনো policy stage), shared-dylib install-before-FATE ordering, n-prefix version checker, diagnostic output reservation, filter spelling এবং missing frame-count query। Fix-এর পরে প্রয়োজনীয় stage পুনরায় যাচাই হয়েছে; valid core objects/media cache পুনর্ব্যবহার করা হয়েছে।

Owner-এর সর্বশেষ নির্দেশে current runs-এ pressure/headroom/swap checks explicitভাবে ignored ছিল। Sampled per-job footprint, disk/mount/timeout/output checks চালু। কোনো unrelated user job/app থামানো হয়নি। Future normal invocation-এর default policy বহাল।

Final shutdown regression: Python 3.14-এর short-lived metadata child-এর process-group PermissionError race ঠিক হয়েছে। কেবল owned child-কে direct signal দিয়ে reap করা হয়; pipes exception হলেও close হয়। Regression ও 20টি real output-limit cleanup repetition পাস।
