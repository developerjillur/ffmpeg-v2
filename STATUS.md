# বর্তমান অবস্থা

আপডেট: **৪ নভেম্বর ২০২৬**। Maintainer: **Jillur Rahman**।

**বর্তমান local release 0.6.0**, frozen pair `0.6.0-fc5c8de8ba2a58f7`। Matching HD software jobs-এ encoder/decoder/filter/validation pools 8/2/2/8; nominal encode budget ১৩/১৪। Stable 0.5.0 retained ও default rollback target। Native core/38 dependencies একই; System/Homebrew FFmpeg অক্ষুণ্ণ।

**সর্বশেষ Phase 10:** private x264 source/target tuning-এ active Native-এর তুলনায় 2.9–3.3% কম instructions এবং প্রায় 98.4% কম captured encoder mutex calls। Target decoded video/audio exact match; 8/10-bit progress TSAN, ছয় codec-mode regression, 14 native checks এবং দুই runtime-এ 142 tests pass। 180 controlled-load encodes ও 45 complete workflows-এর wall-clock CI gate পাস হয়নি। Full HD candidate median 10.5156s বনাম active Native 11.6465s / Stock 10.2494s; CI equality পার করে। Source fix experimental; default release অপরিবর্তিত। [পূর্ণ ফল](docs/PHASE10-RESULTS.md), [cold audit](docs/verification/phase10-2026-11-04.json), [register](PHASE10.md)। নিচের নয়-pair benchmark Phase 8-এর সংরক্ষিত ফল।

| নতুন নয়-pair confirmation, প্রতি source 60s | পুরোনো Native | আগের Stock preset | নতুন Native | পুরোনো Native / Stock থেকে সময় কম |
|---|---:|---:|---:|---:|
| 1920×1080 / 30fps | 9.6969s | 9.7344s | 7.5339s | 22.31% / 22.61% |
| Live-action/VFX 1920×800 / 24fps | 7.7771s | 7.5278s | 5.3840s | 30.77% / 28.48% |

সব full-frame quality/size ও পুরোনো preset-এর paired speed gates pass। একই নতুন tuning-এ Stock control HD 6.8781s / ToS 5.4297s; Native median +9.53%/−0.84%, উভয় 95% interval equality পার করে। Adjacent compressed-path isolation-এ HD audio/video median +1.19%, interval equality পার করে; raw-feed control +4.44% ধীর রয়ে গেছে। Universal native-core superiority দাবি নেই।

দুই runtime-এ final **131টি করে test**; fresh advanced 17, checkpoint/fault 8, source/installed MCP-এর actual eight-thread job, Studio integration এবং actual release lifecycle 10 cases আছে। Existing client configuration unchanged। Full details ও final completion evidence [Phase 8 results](docs/PHASE8-RESULTS.md), [portable index](docs/verification/phase8-2026-11-04.json) ও [register](PHASE8.md)-এ।

নতুন tuning `ffv2` typed jobs/MCP-তে scoped; explicit pools, checkpoint, bitrate, HDR/deinterlace, 4K/resize ও অন্য CPU-তে আগের profile/conservative behaviour থাকে। নিচের Phase 4–7 ফল 0.5.0-এর সংরক্ষিত ইতিহাস।

## সংরক্ষিত Phase 4–7 — 0.5.0

তৎকালীন frozen release `0.5.0-16f948bf021bd8b7`; broader media/recovery/compatibility gates-এর original proof নিচে।

## 0.5.0-এর ফল

| বাস্তব 60s workload | v0.4 workflow/native | নতুন workflow/native | সময় কম |
|---|---:|---:|---:|
| 1920×1080 / 30 fps | 11.4474s | 9.4152s | 17.75% |
| 3840×2160 / 30 fps | 42.9435s | 35.6815s | 16.91% |
| 4K → 1080p | 13.6547s | 11.6713s | 14.53% |
| Live action 1920×800 / 24 fps | 10.4406s | 7.9022s | 24.31% |

পাঁচ paired trial ও প্রতি profile/configuration একটি excluded warmup; 72 output rehashed, 60 measured output। চার profile-ই predeclared quality/size ও paired speed gate pass। Source corpus ও native engine একই রেখে workflow tuning মাপা হয়েছে।

একই নতুন workflow-তে native/Stock median সময় 1080p-তে +1.09%, UHD-তে −0.97%, resize-এ −2.12%, live action-এ +6.28%। চার confidence interval-ই equality পার করে; universal native speed advantage প্রমাণিত নয়। File-size পরিবর্তন −0.015% থেকে +0.005%; নতুন compression algorithm নয়। Sampled memory peak parallelism-এর সঙ্গে বেড়েছে। [Full tables, quality, memory ও intervals](docs/PHASE4-7-RESULTS.md)।

## গ্রহণযোগ্যতা

- নয়টি typed operation; নতুন concat/copy/normalize, বাংলা SRT/ASS subtitle, sample-accurate mixing ও alpha/16-bit/HDR image presets।
- 17 actual advanced workflow/error checks; independent packet/PTS/PCM/pixel proof। Metadata-বিহীন publisher HDR refuse হয়েছে।
- Validated CFR segment checkpoint, continuous AAC, corruption rebuild/reuse ও safe priority yield; 8 actual recovery/failure cases।
- তিন real 180s export: 540s source, 15,120 decoded frames। Actual 30-minute elapsed soak: 54,000 frames, 355 durable sampled records।
- 9 actual install/update/rollback cases; old installed/source MCP refusal, queued/running fences, cross-code checkpoint refusal, rollback-এ validated segment reuse ও 3,600-frame output।
- Final Python 3.9.6/3.14.7-এ 126 tests করে; task memory waiver default-policy tests থেকে isolated।
- Native base 14 ও extended 21 checks; compiled libass build-এর 2,893 local FATE records/zero failures; 15 selected external targets।
- 15 format cases; source-codec audit actual plans থেকে। Full external 5,554-target suite চালানো হয়নি।
- Installed CLI-তে চার long-profile output quality-approved benchmark file-এর সঙ্গে byte-identical।
- Installed exec দিয়ে existing Studio export, retained-part identical recovery ও tamper refusal; existing source/asset files reused ও unchanged।
- Existing client entry-তে installed launcher; input roots/অন্য settings preserved, private backup retained। Fresh configured MCP server 0.5.0-এ complete queue/worker/PCM/mix/replay/priority/cancel/refusal acceptance।
- এই chat-এর connected tools দিয়েও actual PCM export ও idempotent replay পাস; final installed fresh connection পৃথক proof। Hot reload-এর version guarantee দাবি নেই।
- 45 frozen package files ও 38 binary/non-system library bindings। Native C source `b6e0de6…` clean; new private libass configuration, নতুন C algorithm নয়।

[19-requirement register](PHASE4-7.md), [portable evidence](docs/verification/phase4-7-2026-11-03.json), [operations](docs/OPERATIONS.md), [contracts](docs/PHASE5-7-DESIGN.md)।

## Policy ও সীমা

Task media jobs-এ owner-এর explicit RAM waiver scoped ছিল। Runtime default, sampled 12 GiB job footprint, disk/mount/time/output checks ও sequential heavy work বহাল। Unrelated apps/services বন্ধ করা হয়নি; T7 originals অক্ষুণ্ণ।

30-minute soak overnight/kernel guarantee নয়। Perceptual HDR mastering, arbitrary private-camera corpus, full external FATE, other platforms/codec calibration, reproducible public distribution ও public release tested scope-এর বাইরে। Custom-state release commands-এ একই `--state-dir` দিতে হয়। [Known gaps](docs/GAPS.md) ও [readiness](docs/READINESS.md)।

Historical [Phase 2](docs/PHASE2-RESULTS.md) ও [Phase 3](docs/PHASE3-RESULTS.md) proof সংরক্ষিত; short এবং long benchmark epochs মেশানো হয়নি।
