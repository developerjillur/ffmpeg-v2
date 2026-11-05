# Phase 9 — HD ও raw-input performance investigation

৪ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**।

**Performance fix গৃহীত হয়নি; installed 0.6.0 বহাল।** একাধিক বাস্তব optimization compile/run করা হয়েছে। Quality বজায় থাকলেও independent speed gate পেরোয়নি। Phase 9-এর মূল faster-than-Stock লক্ষ্য এখনো সম্পন্ন বলা যাচ্ছে না।

Cold audit সম্পন্ন: **329টি actual encoding run, 457,200 encoded frames**, দুই Python runtime-এ 136টি করে test, fresh configured installed MCP checks এবং 20টি owned state database-এ **শূন্য active job**। [Machine-readable verification index](verification/phase9-2026-11-04.json)-এ original evidence paths ও SHA-256 retained।

## বর্তমান unchanged 0.6.0 বনাম একই tuning-এর Stock

| Workload | Native median | Stock median | Native slowdown | Whole-block 95% ratio interval |
|---|---:|---:|---:|---:|
| 60s 1080p complete workflow | 20.253467s | 18.729960s | **+8.13%** | **1.002463–1.095704** |
| 30s raw → x264 encoding | 7.931870s | 7.477305s | **+6.08%** | **0.998554–1.277643** |

HD-তে ৩টি ABBA/BAAB block-এ ৬টি measured run/engine এবং ১টি excluded warmup/engine; মোট ১৪টি complete jobs। Raw-তে ৪ block, ৮ measured run/engine ও excluded warmups; মোট ১৮ encodes। Native ও Stock-এ lookahead 2-সহ সব encoder settings এক; HD-র সব published output পুরোনো quality-approved SHA-এর হুবহু সমান। Raw-ও retained reference output-এর exact SHA দিয়েছে।

এই HD study-তে Native ধীর ছিল; interval-ও 1-এর উপরে। Raw interval equality পার করেছে। উভয় target-এর gap-closed gate fail। আগের +9.53%/+4.44% এবং বর্তমান +8.13%/+6.08% ভিন্ন host epoch-এর ফল; production code অপরিবর্তিত থাকায় এই percentage change-কে নতুন code speedup ধরা যাবে না। Absolute seconds-ও ভিন্ন epoch-এর সঙ্গে সরাসরি speed claim-এর জন্য মেশানো যাবে না। ছোট block count-এর scope বজায় আছে।

## Baseline ও পদ্ধতি

Frozen SDK `v0.6.0 / a8e44c8a725eb20279072654e5f5a35b7e961a8e`; active local release `0.6.0-fc5c8de8ba2a58f7`। Native source `b6e0de6e580ae325d5b12df79dddd364ccf11efb`, same M4 Max build ও Homebrew Stock 9.0.2। দুই engine একই x264 library ব্যবহার করেছে। Target BBB 1920×1080/30fps-এর 60–120s এবং তার 60–90s-এর retained raw reference। Raw reference 900 frames/2,799,360,000 bytes; নতুন duplicate raw তৈরি হয়নি।

Encoder/decoder/filter/validation pools 8/2/2/8, CRF 20, veryfast, native geometry, software decode/filter অপরিবর্তিত। যে experiment lookahead বদলেছে, Stock control-ও একই lookahead নিয়েছে। Native-only queue depth experiment আলাদা implementation control; Stock-এ unsupported flag পাঠিয়ে সমতুল্য queue দাবি করা হয়নি।

Initial warmup excluded, সব slow trial retained। Native/Stock adjacent ABBA/BAAB blocks; HD candidate confirmation-এ baseline Native/candidate Native/candidate Stock-এর rotated symmetric blocks। 20,000 bootstrap draws-এ পুরো adjacent block resample হয়েছে। ভিন্ন epoch একত্র করে দ্রুততম ফল বাছা হয়নি। HD full workflow-তে planning, encode, strict complete decode, hash ও atomic publish অন্তর্ভুক্ত; raw diagnostic encoding stage মাত্র।

## কোনো code change ছাড়াই baseline-এর ফল বদলেছে

| Epoch / workload | Native/Stock median ratio | Slowdown | Block-bootstrap 95% interval |
|---|---:|---:|---:|
| প্রথম reproduction, HD encoding | 1.082596 | +8.26% | 0.9927–1.1679 |
| পরের filter study-এর unchanged HD control | 0.925943 | −7.41% | 0.9242–0.9372 |
| Probe study-এর unchanged HD control | 0.997339 | −0.27% | 0.9427–1.0134 |
| প্রথম reproduction, raw encoding | 0.987311 | −1.27% | 0.9446–1.0565 |
| Independent raw confirmation, 8 runs/engine | 1.060793 | +6.08% | 0.9986–1.2776 |

প্রথম reproduction-এ HD retired-instruction ratio 0.99166, cycle ratio 0.99708 ও CPU-seconds ratio 0.99816, তবু elapsed ratio 1.08260। একই code-এর অন্য epoch-এ CPU time ও elapsed time দুটোই অনেক বদলেছে। এগুলো busy-host execution/scheduling state-এর প্রভাব দেখায়। নির্দিষ্ট thermal, frequency, অন্য application বা একটি C function-এর causal শতাংশ প্রতিষ্ঠা হয়নি। পুরোনো +9.53% ও +4.44% ফল retained; নতুন run দিয়ে মুছে ফেলা হয়নি।

## বাস্তবে চেষ্টা করা optimization

| পরিবর্তন | ফল | সিদ্ধান্ত |
|---|---|---|
| Identity scale সরানো | Exact same encoded SHA; HD native median 4.911→5.131s | লাভ প্রমাণিত নয়; default retained |
| Stream probing বাদ দেওয়া | Same output; HD/raw throughput লাভ দেখায়নি | Input probing retained |
| Scheduler frame queues 2/4/8/16 | 80 runs; queue 16 HD/raw ratios 0.9971/0.9908, intervals equality পার করে | Native candidate unpromoted; original queue 2 retained |
| x264 lookahead threads 2→1 | Calibration HD −8.85%, raw +19.02% | HD-only candidate স্বাধীনভাবে যাচাই করা হয়েছে |
| Lookahead 1 ও sync-lookahead 0 | Calibration HD +4.17%, raw +21.77% | নির্বাচিত হয়নি |

Queue candidate decoder hardware-pool extra-frame accounting-ও একই capacity অনুযায়ী বদলায়। শুধু queue বড় করে fixed hardware frame pool-এর হিসাব ভাঙা হয়নি। Candidate default 2 ছিল; পরীক্ষায় explicit 4/8/16 দেওয়া হয়েছে। এটি নতুন production engine নয়; original source/build/install অপরিবর্তিত। Experimental incremental build baseline-এর generated version header reuse করেছে; candidate-এর পরিচয় source commit/patch/binary SHA, নতুন release banner নয়।

## HD lookahead candidate-এর independent complete workflow

প্রতি configuration ১টি excluded warmup ও ১০টি measured run; ৫টি symmetric block, মোট ৩৩টি actual jobs। Calibration-এর দ্রুত ফল production improvement হিসেবে ব্যবহৃত হয়নি।

| Configuration | Total median | Encode median | Strict-decode median |
|---|---:|---:|---:|
| Frozen 0.6.0 Native, lookahead 2 | 13.0545s | 11.0271s | 1.6389s |
| Experimental Native, lookahead 1 | 18.2682s | 15.6844s | 1.8691s |
| Matching Stock, lookahead 1 | 15.3995s | 12.9092s | 1.8737s |

Candidate/frozen Native ratio **1.399376**, paired 95% **1.1583–1.6227**: এই run set-এ candidate **39.94% ধীর**। Candidate/matching Stock ratio **1.186288**, interval **0.9772–1.4210**। Candidate-কে দ্রুততর default করা যাবে না। Frozen Native এবং lookahead-1 Stock-এর tuning আলাদা; ওই দুই row দিয়ে default-এর same-tuning Stock advantage দাবি করা যাবে না।

| All-frame quality / size | Candidate বনাম frozen Native | Gate |
|---|---:|---|
| Frames | 1,800 / 1,800 | Pass |
| VMAF delta | −0.008504 | Pass, ≥−0.10 |
| PSNR-Y delta | −0.000460dB | Pass, ≥−0.05dB |
| SSIM delta | +0.000002 | Pass, ≥−0.00001 |
| Size ratio | 0.998895, অর্থাৎ 0.1105% কম | Pass, ≤1.02 |
| Independent speed | +39.94% slower | **Fail** |

Native ও matching Stock-এর candidate output SHA এক। নতুন candidate-এর metric সব frame-এ নতুন করে মাপা হয়েছে; আলাদা encoded SHA-এর জন্য পুরোনো VMAF reuse করা হয়নি। Quality pass speed gate-কে বাতিল করে না।

## Verification ও release action

| Check | ফল |
|---|---|
| Python 3.9.6 | 136 tests pass |
| Python 3.14.7 | 136 tests pass |
| Default memory-policy controls | Task waiver সরিয়ে test করা হয়েছে |
| Fresh configured installed MCP | Handshake-এর 8 tools, queue/worker/output, cancel, priority, mix, schema/path/budget refusals pass |
| Retained media | 329 encoding output cold SHA-256 audit pass |
| Owned queue states | 20 databases checked, 0 queued/running/validating/waiting job |
| Production package | Frozen 0.6.0 allowlist-এর byte hashes unchanged |
| Native install ও dependencies | Cold selected 38-file engine verification pass |
| New performance release | **হয়নি; কোনো candidate speed gate পেরোয়নি** |

নতুন native patch promote হয়নি বলে নতুন GPU/FATE acceptance বা নতুন binary release দাবি করা হয়নি। Installed release/code-engine pair একই verified 0.6.0; Phase 9-এ rollback করার মতো activation হয়নি। Source-এ গবেষণা, reproducible runners, statistical tests ও unpromoted patches যোগ হয়েছে।

## Root-cause অনুসন্ধান কী প্রতিষ্ঠা করেছে

Actual x264 open-এ দুই engine-এ frame threads 8, lookahead 2, sync depth 4, RC lookahead 10, CPU dispatch 202। Worker QoS 21 ও priority 31; প্রথম picture strides 1920/960/960 এবং plane alignment modulo 128 সব শূন্য। এসবের মধ্যে Native/Stock mismatch পাওয়া যায়নি।

সব frame-এর দ্বিতীয় observer-এ raw input-এর call-between gap Native/Stock **0.025730/0.028382s**, x264-call total **4.708488/4.449275s**। এই sample-এ Native-এর অতিরিক্ত সময় প্রধানত একই x264 implementation-এর call-এর ভেতরে ছিল। Serialized raw feed/frame-copy bottleneck-এর সমর্থন মেলেনি। Call wall time worker execution ও wait একসঙ্গে ধরে; CPU availability বনাম synchronization-এর causal ভাগ প্রতিষ্ঠা হয়নি। HD sample-এ আবার Native দ্রুত ছিল। Instrumented timings final performance ফল নয়।

## বর্তমান সীমা ও পরবর্তী প্রয়োজন

নির্ভরযোগ্যভাবে 9.53% ও 4.44% অপসারণ দাবি করা যাচ্ছে না। কোনো experimental default activate হয়নি, নতুন performance version/tag প্রকাশ হয়নি। বেশি queue বা কম lookahead-কে generic speed fix করার evidence নেই। Controlled CPU-load replay এবং per-worker execution/wait accounting ছাড়া busy-host tail-এর কোন অংশ Native code দিয়ে ঠিক করা যাবে তা অমীমাংসিত। এই report-এ system scheduling-কে একমাত্র নিশ্চিত কারণ বলা হয়নি।

[পূর্ণ research ও প্রথম-party সূত্র](PHASE9-RESEARCH.md), [মূল gate register](../PHASE9.md), [queue experiment patch](experiments/phase9-frame-queue-capacity.patch), [lookahead experiment patch](experiments/phase9-hd-lookahead.patch)। সব media/build data mounted `<LAB_ROOT>/ffmpeg-v2-phase9`-এ retained; original assets ও installed release preserved।
