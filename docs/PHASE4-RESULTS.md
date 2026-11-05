# Phase 4 — বাস্তব HD/UHD calibration

Maintainer: **Jillur Rahman**। তারিখ: ৩ নভেম্বর ২০২৬। Baseline: **v0.4.0 / 24b2ac6**। নিচের সংখ্যা frozen calibration runs-এর; নতুন release-এর শেষ acceptance আলাদা index-এ থাকবে।

## একই native engine-এ workflow

প্রতি কাজ ৬০ seconds media, start=৬০ seconds। প্রথম warmup বাদ দিয়ে ৫টি paired trial, seeded interleaving, একই Mac ও ব্যস্ত host। Timing-এর মধ্যে probe, queue, encode, complete decode, SHA-256 ও atomic publication আছে।

| বাস্তব workload | Baseline median | Tuned median | সময় কমেছে | Paired bootstrap 95% ratio | Quality/size gate |
|---|---:|---:|---:|---:|---|
| BBB native 1920×1080 / 30 fps | 12.3745 s | 9.3110 s | 24.76% | 0.6028–0.9260 | Pass |
| BBB native 3840×2160 / 30 fps | 45.1621 s | 36.5803 s | 19.00% | 0.7566–0.9035 | Pass |
| BBB 3840×2160 → 1920×1080, filter pool 4 | 17.3587 s | 14.0851 s | 18.86% | 0.7785–0.9335 | Pass |
| Tears of Steel live action 1920×800 / 24 fps | 10.7801 s | 7.5729 s | 29.75% | 0.6578–0.9300 | Pass |

Tears of Steel-এর coded height **800**; এটিকে পূর্ণ 1080-height footage বলা হচ্ছে না। BBB-তে প্রকৃত 1080 ও 2160 source ব্যবহৃত হয়েছে। Publisher ZIP size, HTTPS object identity, extracted movie SHA-256/CRC ও licence context corpus receipts-এ আছে।

## Stock FFmpeg-এর সঙ্গে একই tuning

| Workload | Native বনাম Stock median time | ফলের সীমা |
|---|---:|---|
| 1080p | 2.22% বেশি | এই run-এ Stock দ্রুত; native-এর universal superiority প্রমাণ হয়নি |
| 2160p | 7.85% কম | Confidence interval সমান সময় অতিক্রম করে |
| 2160p → 1080p / filter 4 | 8.42% কম | Confidence interval সমান সময় অতিক্রম করে |
| Live action | 0.11% কম | পার্থক্য অনিশ্চিত |

এই matched software settings-এ native ও Stock encoded files-এর SHA-256 সমান ছিল। তাই তাঁদের quality metrics একই file identity দিয়ে reuse করা হয়েছে। Native kernel নিজে সব কাজে দ্রুত—এমন সিদ্ধান্ত এই ফল থেকে আসে না।

## যেসব tuning promote হয়নি

- Encoder threads 2→4 একা UHD-তে median 1.34% কমালেও interval 1 অতিক্রম করেছে। সেই একক পরিবর্তন promote হয়নি।
- Resize-এ filter pool 2-এর প্রথম run median 12.49% কমালেও interval 1.0719 পর্যন্ত গিয়েছিল। আলাদা filter-pool-4 run আগে থেকে নির্ধারিত একই quality/size gates পাস করার পর resize policy নির্বাচিত হয়েছে।
- ৬০-second hardware scaling-এ সময় মাত্র 1.56% কমেছে, interval 0.8218–1.0222; VMAF **6.4519**, PSNR-Y **3.8414 dB**, SSIM **0.001838** কমেছে। Hardware scaling default হয়নি। Explicit opt-in এখনও আছে।

## Default policy ও quality

M4 Max-এর measured দীর্ঘ software workload-এ encoder=4, decoder=2, validation=4; native-size filter=2, resize filter=4। Explicit settings অগ্রাধিকার পায়। Policy সীমিত: ≥60 seconds, একই native integer frame rate ≤30, known 8-bit 4:2:0, software decode/filter, output width ≥1920, HDR/deinterlace conversion ছাড়া। অন্য কাজ conservative থাকে।

আগে থেকেই নির্ধারিত gates: ΔVMAF ≥−0.10, ΔPSNR-Y ≥−0.05 dB, ΔSSIM ≥−0.00001, output size ratio ≤1.02; median কম ও paired bootstrap upper bound <1। প্রতি profile-এ সব 1800/1440 frame aligned reference-এর সঙ্গে মাপা হয়েছে। নতুন default CLI-র চার output-ই corresponding quality-approved tuned file-এর সঙ্গে **byte-identical** হয়েছে।

Warmup-এর সংখ্যা আলাদা আছে; এটি OS disk cache সম্পূর্ণ খালি করা cold-disk পরীক্ষা নয়। Thread tuning-এর জন্য measured কাজের বাইরে throughput প্রতিশ্রুতি নেই।

## Evidence

সব path `<LAB_ROOT>/ffmpeg-v2-phase4/`-এর অধীনে:

| Evidence | Artifact |
|---|---|
| Source corpus | `corpus/{bbb-1080,bbb-2160,tos-1080-blender}.receipt.json` |
| Encoder-only calibration | `calibrate-20261103T082208-0d3797b9/{report,analysis}.json` |
| Balanced 4-profile / Stock | `balanced-20261103T084556-25ed478b/{report,analysis}.json` |
| Resize filter=4 correction | `balanced-20261103T091601-c5d721a8/{report,analysis}.json` |
| Long hardware scaling | `hardware-20261103T092818-fb9b4785/{report,analysis}.json` |
| Actual default CLI equality | `default-cli-20261103T093520-224a8c7d/report.json` |

Runner, package sources, source ranges, binary closure IDs, argv, stage timings ও প্রতিটি actual output receipt raw reports-এ আছে। Research/primary links: [PHASE4-RESEARCH.md](PHASE4-RESEARCH.md)।
