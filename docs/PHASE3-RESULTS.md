# Phase 3 comparison — FFmpeg-v2 0.4.0

৩ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Baseline **v0.3.0 / d3128af**; native core **n9.0.2-3-gb6e0de6-ffmpeg-v2-m4** অপরিবর্তিত। সব বড় run sequential; owner-এর scoped RAM waiver recorded।

Software pipeline-এর repeated discovery/resource overhead কমেছে। ১৫-trial matched pipeline-এ native median **1.124668 → 0.883535s, 21.44% সময় কম**। পৃথক ৯-trial পূর্ণ CLI process-এ **1.038100 → 0.853827s, 17.75% সময় কম**। Stock-এর ওপর স্থায়ী native encoder advantage এই busy-host measurements প্রতিষ্ঠা করে না।

## Stock বনাম native: একই validation workflow

সব ক্ষেত্রে 6s 1280×720/30fps FFV1/PCM input, software libx264 veryfast, 4Mbps, একই codec/filter thread limit, metadata, full decode, SHA-256 ও atomic publication। Stock হলো installed FFmpeg 9.0.2 binary-কে এই workflow-তে চালানো। Raw FFmpeg encode সময় আলাদা column-এ আছে।

| Run | measured trial/config | Stock median | Native median | Native সময়ের পার্থক্য |
| --- | ---: | ---: | ---: | ---: |
| সংরক্ষিত Phase 2 full pipeline | 5 | 1.464336s | 1.599936s | +9.26% |
| Fresh frozen Phase 2 pipeline | 15 | 1.082556s | 1.124668s | +3.89% |
| Phase 3 full pipeline | 15 | 0.855254s | 0.883535s | +3.31% |
| Phase 3 পূর্ণ CLI process | 9 | 0.883975s | 0.853827s | −3.41% |

৯.৩% historical result নতুন runs-এ একইভাবে পুনরাবৃত্ত হয়নি। Phase 3 pipeline native/stock ratio-এর paired bootstrap 95% interval **0.95584–1.29336**, পূর্ণ CLI-এর **0.95278–1.06079**; দুটোই 1 পার করে। তাই persistent regression শূন্য বা universal native speedup কোনোটিই confirmed নয়। Overhead fix বাস্তব; stock/native ranking-এ shared-host noise আছে। Historical ও fresh run সরাসরি এক ratio-তে মেলানো হয়নি।

## একই engine-এ Phase 2 → Phase 3

১৫টি measured trial/config, প্রতি configuration-এ একটি excluded warmup। Fixed-seed interleaved order; চারটি case sequential। সব সংখ্যা seconds।

| পর্যায় | Stock Phase 2 | Stock Phase 3 | Native Phase 2 | Native Phase 3 |
| --- | ---: | ---: | ---: | ---: |
| Capability discovery | 0.135415 | 0.001549 | 0.162062 | 0.001927 |
| Source probe + planning | 0.030107 | 0.028806 | 0.032656 | 0.037617 |
| Worker pass | 0.880767 | 0.814743 | 0.901245 | 0.831445 |
| Encode media process | 0.485729 | 0.475727 | 0.498781 | 0.481545 |
| Full-decode media process | 0.205614 | 0.198293 | 0.204561 | 0.208308 |
| Integrity + publication | 0.037852 | 0.006215 | 0.034293 | 0.006695 |
| Full pipeline | **1.082556** | **0.855254** | **1.124668** | **0.883535** |
| Benchmark subprocess wall | 1.173493 | 0.930053 | 1.197140 | 0.951847 |

প্রতি column-এর median স্বাধীন; stage medians যোগ করলে total median হওয়ার কথা নয়। Native discovery সময় **98.81%** কমেছে; এটি পুরো encode-এর 98.81% speedup নয়। একই run-এ full pipeline stock সময় −21.00%, native −21.44%। Native time-ratio bootstrap interval **0.76107–1.02560**; outlier ছিল। Preliminary ১৫-trial candidate-এ native সময় −16.57%, interval 0.78225–0.92757। দুই run-ই সংরক্ষিত; final report-এর অনুকূলে preliminary result বেছে নেওয়া হয়নি।

Final pipeline native range **0.766998–2.363586s**; stock **0.766860–1.677409s**। এগুলো load-sensitive, short synthetic benchmark। Default ও explicit custom-binary warm cache উভয় engine-কে সাহায্য করে।

## প্রকৃত CLI path

একই চার configuration-এর ৯ measured trial ও প্রতি case-এ একটি warmup। `cli.main` parser, spec read, submit, worker ও JSON result সম্পূর্ণ চলে; process wall-এ interpreter/import/entry overhead আছে। Explicit binary selection ব্যবহার হয়েছে; native default JSONL ও stock kv progress বজায় আছে। এটি আগের matched-kv pipeline run থেকে পৃথক measurement।

| Engine | Phase 2 CLI process | Phase 3 CLI process | সময় কম |
| --- | ---: | ---: | ---: |
| Stock | 1.058894s | 0.883975s | 16.52% |
| Native | 1.038100s | 0.853827s | **17.75%** |

CLI function body native 0.977850 → 0.790082s, **19.20%** কম। তার paired bootstrap ratio interval 0.71544–0.88746। Stock/native CLI comparison-এর uncertainty আগের table-এ আছে।

## Output ও quality

| পরীক্ষা | ফল |
| --- | --- |
| Final pipeline outputs | 64/64 completed, এক whole-file SHA-256 |
| Actual CLI outputs | 40/40 completed, একই software bytes/hash |
| Output size | **3,082,562 bytes**, stock ও native সমান |
| Decoded video | Stock/native-এর 180/180 frame hash সমান |
| Earlier measured software file | একই SHA-256; aligned quality evidence reuse বৈধ |
| Software VMAF / SSIM / PSNR-Y | **97.521175 / 0.999420 / 46.860962 dB** |
| অতিরিক্ত compression | **0%**; এই release workflow speed ও reliability উন্নত করেছে |

Quality score নতুন করে বানানো হয়নি: একই source ও byte-identical output-এর আগের 180-frame metric receipt reuse করা হয়েছে। Full metadata/decode/hash/publication প্রতিটি নতুন job-এ হয়েছে।

Cold-cache integrity inspection বাদ যায় না। Final isolated cold/warm spot check: stock **0.405864 / 0.001237s**, native **0.556707 / 0.001735s**। Respectively 21/28 binary ও non-system dependency files; active selection ffplay-সহ 30 files। Cold spot check একটি sample, benchmark confidence estimate নয়। Library SHA-256 cold inspection-এ পুনরায় মিলিয়ে `ctime_ns`-সহ bind করা হয়; warm hit-এ identity/load-path/OS check থাকে।

## Hardware scaling: default-এ promote হয়নি

একই native binary, forced VideoToolbox decode/encode, synthetic 3s 3840×2160 8-bit SDR H.264 →1920×1080 H.264/6Mbps; ৭ measured trial ও একটি excluded warmup/path। Quality common Lanczos-downscaled reference-এর 90 aligned frame-এ measured।

| বিষয় | CPU download + software scale | Hardware frames + scale_vt |
| --- | ---: | ---: |
| Full call median | **1.437625s** | 1.520887s |
| Encode process median | **0.903715s** | 1.001803s |
| Output bytes median | **2,125,713** | 2,187,724 |
| VMAF | **95.412413** | 92.857359 |
| SSIM | **0.999606** | 0.998741 |
| PSNR-Y | **48.467918 dB** | 43.423006 dB |

এই fixture-এ hardware path full call **5.79% ধীর**, VMAF প্রায় **2.56 point কম**। তাই `filter_backend=software` default। Explicit `videotoolbox` option supported ও validated, কিন্তু faster/quality-equivalent দাবি নেই। 10-bit, HDR, rotation, non-square pixels ও CPU-filter combinations typed refusal পায়। Wider/longer natural-media tuning পরের evidence gate।

## Reliability ও interface

- **102 control tests**, Python **3.9.6 ও 3.14.7**—দুই runtime-এ pass।
- **32 actual acceptance checks**: 14 native-media, 12 colour/interlace/VFR/error/GPU matrix, 3 existing fault drills, 1 MCP lifecycle/priority, 2 নতুন scaling/supervisor-loss checks।
- নতুন supervisor SIGKILL drill-এ জীবিত worker জন্ম-পরিচয়/nonce/owner যাচাই করে নিজস্ব media group থামিয়েছে। Media gone, final output absent, host lock released। Reused PID/wrong nonce-এ signal দেওয়া হয় না।
- `priority=-10..10`, additive legacy DB migration, FIFO/aging, restart/idempotency/explicit-ID controls pass। Real MCP-এ urgent job আগে complete হয়েছে।
- Custom dependency cache hit/refresh/corruption, library alias retarget, OS change, restored-mtime source/library edits ও cold hash-race regressions pass।
- Native API no-helper sampling, ABI layout, live child discovery, fallback ও unavailable metadata measurement-এর fail-closed cleanup pass।

Native core বদলায়নি, তাই নতুন FATE run দাবি নেই। একই binary-এর Phase 2 **2,893 local FATE records / zero failure** historical acceptance বহাল; active 30 files-এর hashes আবার মিলেছে। Full external-sample FATE, overnight reliability ও private HDR/camera/perceptual acceptance পৃথক।

## সংরক্ষিত প্রমাণ

Portable checksums ও summary: [phase3-2026-11-03.json](verification/phase3-2026-11-03.json)। Private raw reports ও successful/failed diagnostics project/NexaWork-এ রাখা হয়েছে; public push বা hosted release হয়নি।

- Final software pipeline: `<LAB_ROOT>/ffmpeg-v2-phase3/software-20261103T021617-2682f88f/report.json`
- Actual CLI: `<LAB_ROOT>/ffmpeg-v2-phase3/software-cli-20261103T022043-b7f530ec/report.json`
- Preliminary candidate: `<LAB_ROOT>/ffmpeg-v2-phase3/software-20261103T021130-3a6e7b4c/report.json`
- Scaling ও supervisor loss: `<LAB_ROOT>/ffmpeg-v2-phase3/acceptance-20261103T021532-5c33115c/report.json`
- Regression index: `<LAB_ROOT>/ffmpeg-v2-phase3/regressions-20261103T021838/report.json`
- Final control: `<LAB_ROOT>/ffmpeg-v2-phase3/control-final-20261103T022217/report.json`
- Final cold/warm cache: `<LAB_ROOT>/ffmpeg-v2-phase3/cache-final-20261103T022259/report.json`

Remaining work: stock/native advantage-এর stronger low-noise long/natural benchmark, calibrated hardware scaling, private HD/HDR display review, overnight soak, typed subtitle/concat contracts, preemption ও production integration। [সম্পূর্ণ gap register](GAPS.md) এই সীমাগুলো ধরে রাখে।
