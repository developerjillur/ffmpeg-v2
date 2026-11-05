# Phase 10 — verified source efficiency, elapsed gap এখনও অপ্রমাণিত

Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬।

**ফল:** private x264-এর progress query ও compiler tuning-এ একই content কম instructions-এ encode হয়েছে। Target decoded video/audio exact match। Independent wall-clock confidence gates পাস হয়নি; candidate experimental, active release `0.6.0-fc5c8de8ba2a58f7`।

## Implemented fix

Pinned x264 `b35605ace3ddf7c1a5d67a2eb553f034aef41d55` থেকে atomic acquire/release progress query এবং positive row-wait-এর acquired lower-bound cache। Motion-vector required-line check, positive mutex/condition wait এবং warning/recovery বজায় আছে। Final candidate M4 target ও vectorization ব্যবহার করে; LTO নেই। M4+LTO variant SIGSEGV-তে rejected; receipts ও partial retained।

## Independent encode timing

একই input/argv, 8 encoder / 2 decoder / 2 filter, CRF20/veryfast। 7 balanced blocks × 4 input/load groups × 6 runs = 168 measured encodes; 12 excluded warmups, মোট 180। প্রতি cell-এ প্রতি engine 14 measured runs। No-added-load-কে idle machine বলা হয়নি। CI হলো 20,000 whole-block bootstrap resamples-এর candidate/Stock ratio।

| Workload | Added workers | Active 0.6 encode s | Candidate s | Stock s | Candidate vs Stock | Ratio 95% CI |
|---|---:|---:|---:|---:|---:|---|
| hd60 | 0 | 11.7162 | 9.3688 | 10.6434 | -11.98% time | 0.6695–1.1130 |
| hd60 | 2 | 9.7052 | 8.8659 | 8.5133 | +4.14% time | 0.8955–1.1109 |
| raw30 | 0 | 4.6852 | 4.3968 | 4.7931 | -8.27% time | 0.8015–1.1161 |
| raw30 | 2 | 4.3154 | 4.1893 | 4.2420 | -1.24% time | 0.7696–1.4667 |

সব CI equality অতিক্রম করেছে। ভালো median-কে proven speedup বলা হয়নি; slow runs বাদ দেওয়া হয়নি।

## CPU work ও mutex traffic

| Workload/load | Instructions vs active 0.6 | Instructions vs Stock | Captured x264 mutex reduction bounds |
|---|---:|---:|---|
| hd60/load0 | -2.904% | -3.707% | 98.4399%–98.4404% |
| hd60/load2 | -2.963% | -3.749% | 98.4399%–98.4404% |
| raw30/load0 | -3.089% | -3.052% | 98.4205%–98.4214% |
| raw30/load2 | -3.303% | -3.148% | 98.4196%–98.4215% |

Mutex bounds-এ সব library-র unrecorded callsite overflow-ও candidate-এর বিপক্ষে ধরে হিসাব করা হয়েছে। V5 observer প্রতিটি engine-এর নির্দিষ্ট x264-তেই link করেছে; actual loaded image ও parameter function binding verified। এই instrumented timings speed promotion-এর জন্য নয়। CPU instruction improvement-এ source patch ও private compiler tuning দুটোই আছে; পুরো লাভকে শুধু source patch বলা হয়নি।

## Root-cause evidence

Original Native ও Stock একই Homebrew x264 ব্যবহার করত। Shared macroblock progress-query locking একটি বাস্তব avoidable cost, কিন্তু এটি একা আগের Native/Stock gap-এর ব্যাখ্যা নয়। Public kernel runnable counters-এ ready-but-not-running wait এবং P-core share বদলেছে। Process-only observer-এ pthread hooks বাদ রেখেও এই পরিবর্তন পাওয়া গেছে। Aggregate worker wait-কে elapsed time-এর সঙ্গে সরাসরি যোগ/বিয়োগ করা হয়নি।

Raw profiling-এর একটি baseline run-এ প্রায় 2.80 GB disk read এবং পরের private run-এ প্রায় 1.36 MB পাওয়া গেছে। Process-only replay-তেও original/raw/no-added-load-এ 2.80 GB, candidate-এ 7.75 MB, Stock-এ 0.74 MB। এটি cache residency-র একটি measured imbalance। তাই ওই profiler timing-কে codec speedup বলা হয়নি। আগের 9.53%/4.44%-এর কত অংশ CPU queue, cache বা অন্য কারণে—তার exact causal percentage এই busy-host experiment নির্ধারণ করে না।

## Full typed 1080p workflow

একই frozen 0.6 SDK, 8/2/2/8 pools, planning → encode → strict full decode → hash → no-clobber publication। Added synthetic load নেই। 3 excluded warmups + 42 measured runs।

| Engine | Total median s | Encode median s | Validation median s |
|---|---:|---:|---:|
| original | 11.6465 | 9.4891 | 1.5424 |
| candidate | 10.5156 | 8.5874 | 1.3552 |
| stock | 10.2494 | 8.6131 | 1.3274 |

| Workflow comparison | Median time change | Candidate/reference 95% CI | Verdict |
|---|---:|---|---|
| candidate / original | -9.710% | 0.7285–1.0263 | Confidence gate pass হয়নি |
| candidate / stock | +2.598% | 0.8255–1.1016 | Confidence gate pass হয়নি |

## Quality ও regression

- HD: সব 1,800 video frame ও 2,813 decoded audio frame-এর timestamps/size/SHA-256 exact match। Raw: সব 900 frame exact match। Container/version metadata 14 bytes ছোট।
- HD VMAF 94.781527, PSNR-Y 47.011742 dB, SSIM 0.998632; raw VMAF 94.920178, PSNR-Y 46.621946 dB, SSIM 0.998291। ΔVMAF/PSNR/SSIM=0। Final candidate-এর metric reuse exact encoded/source SHA ও identical range/fps/argv দিয়ে bound; actual decoded identity নতুন করে মাপা।
- Actual patched frame API-র 8/10-bit ThreadSanitizer: প্রতি depth 524,288, মোট 1,048,576 checks, errors 0; negative pre-publication, positive wait, query ও buffer reuse covered।
- Multiple references/B-frames, 10-bit, sliced, single-thread ও interlaced modes: original/candidate/live-assertion build-এর decoded frames exact match। Non-deterministic mode: strict decode ও safety assertions pass; exact quality equivalence দাবি নয়।
- Native CLI/MCP/media checks: 14 pass। দুই Python runtime: 142/142 tests pass; default memory policy tests task waiver ছাড়া চলেছে।
- Owned verification database audit: 37 databases, active jobs 0। Active installed code/engine hash verified; original native checkout clean।

## Acceptance ও বাকি সীমা

প্রমাণিত ফল হলো source/CPU efficiency ও exact target content preservation। Stock-এর বিরুদ্ধে স্থায়ী wall-clock gap closure এবং default-release promotion এখনও হয়নি। Confidence gate পূরণ না হওয়ায় installation/rollback pointer বদলানো হয়নি। স্থির host/cache conditions-এ নতুন predeclared acceptance window ছাড়া পুরোনো point estimate-কে fixed বলা যাবে না।

Source patches/license: `third_party/x264/`। Detailed method: `docs/PHASE10-RESEARCH.md`। Cold evidence index: `docs/verification/phase10-2026-11-04.json`। External work root: `<LAB_ROOT>/ffmpeg-v2-phase10`। All completed/slow/failed experiment receipts retained।

Exported দুই patch isolated Git index-এ apply করে exact tree `09f3cac3e1d192f70f8b2ca6d13aee552a1aa5b3` পুনর্গঠিত হয়েছে; original source working tree ও main index অপরিবর্তিত। Replay proof cold evidence index-এ linked। Task work directory `du -sh` অনুযায়ী 5.1G; successful ও rejected artifacts retained, cleanup দাবি করা হয়নি।
