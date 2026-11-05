# Phase 8 — 1080p ও live-action software pipeline

Maintainer: **Jillur Rahman**। শুরু: ৩ নভেম্বর ২০২৬। Baseline **v0.5.0 / c3ed158**। Installed 0.5.0 frozen release development checkout থেকে আলাদা থাকে।

## প্রশ্ন ও গ্রহণযোগ্যতা

- [x] আগের +1.09% HD / +6.28% live-action median gap-এর encoding, decode/validation, wrapper ও host variation আলাদা করা; statistical uncertainty বজায় রাখা।
- [x] একই native/Stock libx264 dependency, build flags ও actual sampled CPU stacks পরীক্ষা; profiler timings measured performance থেকে বাদ রাখা।
- [x] বাস্তব 60s BBB 1920×1080/30 ও Tears of Steel 1920×800/24-তে codec/filter/validation calibration; bounded CPU/memory ও sequential work।
- [x] নির্বাচিত tuning-এ full-frame ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05dB, ΔSSIM≥−0.00001, size ratio≤1.02; frames/audio/metadata/full decode/hash/publish retained।
- [x] Independent confirmation-এ native v0.5 ও আগের Stock preset-এর তুলনায় faster median এবং paired bootstrap upper ratio<1; একই নতুন tuning-এ Stock control-ও প্রকাশ। Native core superiority দাবি শুধু সেই control প্রমাণ করলে।
- [x] Explicit overrides/অন্য presets, 4K/resize ও agent/CLI contracts-এর regression; actual installed/default output proof, preserved update/rollback, final report ও source checkpoint।

পুরোনো পাঁচ-trial intervals equality পার করেছে; median difference-কে নিশ্চিত compiler/codec defect ধরে নেওয়া হবে না। Candidate selection calibration থেকে হবে; confirmation নতুন trial-এ। Threshold ফল দেখে বদলাবে না।

## প্রাথমিক প্রমাণ

- Native ও Stock একই `/opt/homebrew/Cellar/x264/r3222/lib/libx264.165.dylib` এবং একই SHA-256 ব্যবহার করে। Native build `-O3`, `-mcpu=apple-m4` ও NEON-enabled; missing optimization flag পাওয়া যায়নি।
- Capability lookup native/Stock প্রায় 2–3ms। আগের live-action encoding medians 6.2049/5.8177s; মোট 7.9022/7.4354s। আগে encoding concurrency ও producer/consumer wait পরীক্ষা করা হবে।
- Frozen source: `<LAB_ROOT>/ffmpeg-v2-phase8/baseline`। Library/source receipt: `initial-bindings.json`; নতুন বড় data শুধু `<LAB_ROOT>/ffmpeg-v2-phase8`-এ।

Native library build বা floating-point flags কেবল measured কারণ থাকলে বদলাবে। Existing corpus ও quality metrics same-file SHA/source/range মিললে reuse হবে। সম্ভাব্য নতুন workload peak 3GiB, calibration/confirmation storage সর্বোচ্চ 8GiB; hard sampled 12GiB job limit ও disk/mount/time safeguards বহাল। Task-এর আগের explicit RAM waiver scoped; unrelated apps/services অপরিবর্তিত।

## প্রথম পক্ষের সূত্র

- [FFmpeg libx264 options](https://ffmpeg.org/ffmpeg-codecs.html#libx264_002c-libx264rgb): encoder threads, frame/slice threading ও CRF আলাদা controls।
- [Clang code generation](https://clang.llvm.org/docs/UsersManual.html#controlling-code-generation): compiler optimization options; actual local `ffbuild/config.mak`-ই এই candidate-এর flags-এর authority।

Diagnostic sampler শুধু task-এর registered PID ও kernel birth identity মিলে attach করবে। Profiled warmup excluded; sampling overhead-সহ timing speed claim-এ ব্যবহার হবে না।

## সমাপ্তি

৪ নভেম্বর ২০২৬: local **0.6.0-fc5c8de8ba2a58f7** installed; stable **0.5.0** rollback target। ছয় requirement-এর [cold evidence index](docs/verification/phase8-2026-11-04.json), [সম্পূর্ণ comparison](docs/PHASE8-RESULTS.md), [কারণ অনুসন্ধান](docs/PHASE8-RESEARCH.md) ও local tag `v0.6.0` আছে। নয়-pair confirmation-এ পুরোনো Native থেকে HD/ToS সময় 22.31%/30.77% এবং আগের Stock preset থেকে 22.61%/28.48% কম; quality/size gates pass। Same-tuned Stock ও raw-feed control-এর সীমিত gaps report-এ retained; সব workload-এ core superiority দাবি নেই।
