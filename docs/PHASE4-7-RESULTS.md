# Phase 4–7 — সম্পূর্ণ স্থানীয় comparison ও acceptance

Maintainer: **Jillur Rahman**। ৩ নভেম্বর ২০২৬। Local release **0.5.0**।

## Performance: দীর্ঘ বাস্তব media

প্রতি কাজ 60s media, start=60s। একই Mac-এ seeded interleaving; প্রতি profile/configuration একটি excluded warmup ও পাঁচটি measured paired trial। Full pipeline-এ probe, queue, encode, full strict decode, SHA-256 ও atomic publish আছে। মোট 72 output-এর checksum আবার মিলেছে; 60 measured output-এর প্রতি software group-এর পাঁচটি file একই bytes।

| বাস্তব workload | v0.4 workflow / native | নতুন workflow / native | নতুন workflow / Stock | আগের workflow থেকে সময় কম | Native/Stock সময় অনুপাত |
|---|---:|---:|---:|---:|---:|
| BBB 1920×1080 / 30 fps | 11.4474s | 9.4152s | 9.3138s | 17.75% | 1.0109 |
| BBB 3840×2160 / 30 fps | 42.9435s | 35.6815s | 36.0309s | 16.91% | 0.9903 |
| BBB 4K → 1920×1080 | 13.6547s | 11.6713s | 11.9244s | 14.53% | 0.9788 |
| Tears of Steel 1920×800 / 24 fps | 10.4406s | 7.9022s | 7.4354s | 24.31% | 1.0628 |

Native/Stock অনুপাত <1 হলে native কম সময় নিয়েছে। নিচের paired interval 1 অতিক্রম করলে ওই engine difference অনিশ্চিত; Stock-এর তুলনায় native-এর universal speed advantage প্রমাণিত নয়। v0.4 baseline ও নতুন workflow একই নতুন native binary ব্যবহার করে, তাই প্রথম দুটি column workflow/thread-pool পরিবর্তন মাপে। Stock column-এ একই নতুন workflow/tuning থাকে।

| Workload | নতুন/আগের workflow 95% ratio | Native/Stock 95% ratio | ΔVMAF | ΔPSNR-Y dB | ΔSSIM |
|---|---:|---:|---:|---:|---:|
| BBB 1920×1080 / 30 fps | 0.6635–0.9188 | 0.9199–1.1069 | -0.012819 | -0.001875 | +0.00000000 |
| BBB 3840×2160 / 30 fps | 0.7741–0.8703 | 0.9145–1.1021 | -0.005929 | +0.000985 | +0.00000000 |
| BBB 4K → 1920×1080 | 0.7398–0.9478 | 0.8794–1.1524 | +0.004358 | +0.000051 | -0.00000200 |
| Tears of Steel 1920×800 / 24 fps | 0.6688–0.8652 | 0.9664–1.1173 | +0.003464 | +0.000373 | +0.00000000 |

সব চার software profile আগে নির্ধারিত ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05 dB, ΔSSIM≥−0.00001, size ratio≤1.02, faster median ও paired upper bound<1 gate পাস করেছে। প্রতি profile-এর সব 1800/1440 frame aligned reference-এ মাপা; quality reuse শুধু একই output SHA/source/range-এ। এটি নতুন compression algorithm নয়।

## Encode, validation ও output size

| Workload | Native encode median | Native full-decode median | Baseline bytes | Native bytes | Size পরিবর্তন |
|---|---:|---:|---:|---:|---:|
| BBB 1920×1080 / 30 fps | 7.6683s | 1.4259s | 20,306,994 | 20,305,248 | -0.009% |
| BBB 3840×2160 / 30 fps | 30.4231s | 4.9787s | 61,007,399 | 60,998,186 | -0.015% |
| BBB 4K → 1920×1080 | 9.7983s | 1.5362s | 21,860,588 | 21,861,741 | +0.005% |
| Tears of Steel 1920×800 / 24 fps | 6.2049s | 1.4095s | 21,373,740 | 21,373,455 | -0.001% |

| Workload | v0.4/native sampled peak median | নতুন/native sampled peak median | নতুন/Stock sampled peak median |
|---|---:|---:|---:|
| BBB 1920×1080 / 30 fps | 279.53 MiB | 328.16 MiB | 327.97 MiB |
| BBB 3840×2160 / 30 fps | 939.85 MiB | 1091.99 MiB | 1091.02 MiB |
| BBB 4K → 1920×1080 | 403.13 MiB | 453.49 MiB | 451.10 MiB |
| Tears of Steel 1920×800 / 24 fps | 206.42 MiB | 245.83 MiB | 245.47 MiB |

Peak column প্রতি measured job-এর encoding/validation sampled tree peak-এর median; পুরো computer-এর memory বা instantaneous GPU peak নয়। CPU energy/power মাপা হয়নি। এই tuning parallelism বাড়িয়ে সময় কমায়; sampled peak memory আগের workflow-এর চেয়ে বেশি হয়েছে।

নির্বাচিত M4 Max long software preset-এ encoder=4, decoder=2, validation=4; native filter=2, resize filter=4। HDR/deinterlace/VFR ও অন্য hardware/geometry-তে এই auto profile অন্ধভাবে প্রয়োগ হয় না। Hardware scaler-এর দীর্ঘ বাস্তব calibration-এ VMAF 6.45 কমেছিল; সেটি default-এ promote হয়নি। [Calibration ও negative results](PHASE4-RESULTS.md)।

## Workflow ও reliability

| Gate | Actual প্রমাণ |
|---|---|
| Phase 5 | 17 positive/error checks: normalized/copy concat packets/PTS, বাংলা SRT/ASS visible timing, PCM sample/gain/offset/loop/limiter, alpha/odd/16-bit PNG/matte, JPEG ও independent HDR pixels |
| Phase 6 | 8 checkpoint/fault cases; corruption rebuild ও reuse, priority preemption, continuous audio packet equality, write-denial retry ও publish reconciliation |
| Long batch | তিন বাস্তব 180s HD/UHD/live-action export; 540s total source, 15,120 decoded frames, sequential queue/idempotency |
| Elapsed soak | 1,799.939s wall clock; 54,000 frame, 1,800.021s output, 355 durable records; sampled job-tree peak 149,440,192 bytes |
| Existing consumer | Actual Studio cut/retime/fade/source-audio export; retained parts retry-তে identical output; tampered request refuse; existing source unchanged |
| Installed CLI/consumer | User-local frozen CLI-তে চার long-profile output একই approved SHA; installed exec দিয়ে actual Studio export/retry/tamper checks |
| Release lifecycle | Actual RC install, queued/running update fences, tampered candidate refusal, version-only update, stale MCP refusal, cross-code retry refusal, rollback checkpoint recovery ও final reactivation/launchers |
| Installed MCP | Existing client entry ও installed final launcher-এ fresh real connection; typed advanced schema, queue/replay/priority/worker/PCM/mix/checksum/cancel/refusals |
| Compatibility | 15 actual format imports/outputs; 2,893 local FATE records ও 15 selected external targets; 5,554 enabled external targets-এর পুরো suite নয় |

দুই Python runtime-এর regression: Python 3.9.6 — 126 tests, Python 3.14.7 — 126 tests। Native base 14 ও extended 21 check বর্তমান library identities-তে পাস। Runtime closure 38 file।

## Scope ও provenance

Timing frozen `0.5.0rc1` functional implementation-এ মাপা হয়েছে। Final `0.5.0`-এ শুধু দুই version literal বদলেছে; অন্য package bytes সমান, final দুই-runtime regression ও installed workflow পৃথকভাবে যাচাই হয়েছে। RC→final bridge original hashes/receipts রাখে।

প্রথম interrupted run-এর চার excluded warmup retained; পরে canonical-path validation gap পাওয়া গেলে দ্বিতীয় run-এর 52 completed output ও stopped partial-ও রাখা হয়। শেষ timing table শুধুই সংশোধিত code-এর নতুন পূর্ণ run থেকে এসেছে। Homebrew libraries-এর device ID বদলালেও 38 content hash ও load path একই পাওয়া যায়; guard বজায় রেখে native/extended/MCP qualification ও explicit activation হয়েছে।

Publisher HDR filename-যুক্ত excerpt-এ colour tags পাওয়া যায়নি; `hdr_metadata_required` refusal পাস করেছে। Positive HDR proof analytic pixel/tag tests; reference-display/perceptual mastering approval নয়। Studio acceptance technical; creative approval বা GUI deployment নয়। Current chat hot reload প্রমাণ নয়; configured fresh MCP connection প্রমাণিত।

Default resource policy অপরিবর্তিত; task-এর explicit RAM waiver scoped। Sampled footprint, disk/mount/time/output checks ও sequential heavy work বহাল। 30-minute soak overnight/kernel guarantee নয়। Full external FATE, arbitrary camera corpus, cross-platform calibration, reproducible public distribution ও public release এই acceptance-এর বাইরে।

Portable [evidence index](verification/phase4-7-2026-11-03.json), [contracts](PHASE5-7-DESIGN.md), [operations](OPERATIONS.md), [research/licences](PHASE4-RESEARCH.md), [acceptance register](../PHASE4-7.md)।

## Original evidence

| Evidence | Original report | SHA-256 |
|---|---|---|
| unit_tests | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase7/unit-20261103T173058-25432940/report.json>) | `ef394d2cc54deb648895870d56dada5d03cea822e5ec505c1636943d578de62f` |
| native_media | [report.json](<<PROJECT>/.runtime/verification/native-media-20261103T164329-59ba0beb/report.json>) | `1047cc2294674680189d8eb2f293493abf4f0028add05528814012fbec10b8c7` |
| extended_media | [extended-acceptance.json](<<LAB_ROOT>/ffmpeg-v2-phase7/candidate-20261103T164329-1231999f/extended-acceptance.json>) | `b5c136b472907e5e988a2b5fa8fc79e111af24c7873ce9d35e4f05d728a7e5c8` |
| performance | [analysis.json](<<LAB_ROOT>/ffmpeg-v2-phase4/acceptance-20261103T170546-0cf42211/analysis.json>) | `e1a5244e1e231e73711d4cdcbb7cfa2bcd43812411bb3d67a69df5e6a8c90e2f` |
| phase5 | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase5/acceptance-20261103T170237-a40ad38f/report.json>) | `067ca36a88784dcf42565fc35c8014011fa4a48b350aacd511e713d48a50d54b` |
| checkpoint | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase6/quick-20261103T170416-3dc3074c/report.json>) | `5ab4f7864c84a5f8d9dc31c83b75527307a8e3667236bea05f18e1c0b096e67a` |
| soak | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase6/soak-20261103T095245-df291d41/report.json>) | `e0c3c0f0beae471a6e1519152283a2e65f0e8c91794982b10873603defc9a457` |
| formats | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase7/formats-20261103T103514-4f5190b6/report.json>) | `0623c03450c40bd60d7864e1626db3ab76614dd134fa67fc3a8a8e7a121cff8a` |
| external_fate | [report.json](<<LAB_ROOT>/ffmpeg-v2-external-fate/run-20261103T103724-3e23f378/report.json>) | `6ebfa644de4ea623516475e1fb81c8b67875a7baf766268a2061d4fd2f9c6dd7` |
| consumer | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase7/studio-20261103T105449-e28b36cc/report.json>) | `5102c0a82026bce05ff78544f405909fe6867884e55d5a827dfbb6620352ae10` |
| lifecycle | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase7/lifecycle-20261103T173037-cf4763d8/report.json>) | `eb5110bb60914eacaaf4b2dadce26aab32414caff067589eedd766afd43605e8` |
| mcp | [report.json](<<PROJECT>/.runtime/verification/mcp-pipeline-20261103T173221-9db290f1/report.json>) | `3ed884c1c4eecaad4cb852c212cfaaeca9118a72fa17c7f1c05b36753a42ecf3` |
| configuration | [config-20261103T173221-e5c824dd.json](<<LAB_ROOT>/ffmpeg-v2-phase7/config-20261103T173221-e5c824dd.json>) | `8e1b5250d8a4980f6937fc214a12b21f7b063d99684b9f39baaa75537540f12d` |
| batch | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase6/batch-20261103T104855-d6511e3a/report.json>) | `d3c666bc42ea3c3fbb40733787df23897a5d5520c45bdc089624315b69ef394b` |
| soak_audit | [endpoint-audit.json](<<LAB_ROOT>/ffmpeg-v2-phase6/soak-20261103T095245-df291d41/endpoint-audit.json>) | `7480d2248e1ef02b267cc64928bf6ac88bef9a930465e7cdb709703ea8749cc8` |
| formats_audit | [source-format-audit.json](<<LAB_ROOT>/ffmpeg-v2-phase7/formats-20261103T103514-4f5190b6/source-format-audit.json>) | `304649c38b5f5c5a8851f12e16cdf0bd650008fa3acec8718ccd2430eca08de9` |
| hdr | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase5/hdr-corpus/excerpt-20261103T104728-b88f1bfc/report.json>) | `8522754a8c3c9d0067ee7a41b341bcaef70fabd9001ec7e276ff695968b2fe4b` |
| installed_default | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase4/default-cli-20261103T173250-5f4a7b43/report.json>) | `429830362ebc16f6d6f91d056c4a7b3a4b0dc02362460a60493822ce96aef8d0` |
| installed_consumer | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase7/studio-20261103T173417-2f7525e3/report.json>) | `fa178ad06a68a787d1938890988a5314691f2523dca78a6874b623709c2a15af` |
| connected | [independent-audit.json](<<PROJECT>/.runtime/verification/connected-mcp-20261103T172752-54caad80/independent-audit.json>) | `d84c55366a290466e6b03200cf99fc6d2cae8a74cb9a19a1b7b52966fb21c18c` |
| timing | [report.json](<<LAB_ROOT>/ffmpeg-v2-phase4/acceptance-20261103T170546-0cf42211/report.json>) | `06fc3057daaa5e9f3c8c263801e6b6866b2ebbabbbd61cdc90f3a68621c032da` |
