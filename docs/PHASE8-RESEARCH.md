# Phase 8 — কারণ অনুসন্ধান ও tuning contract

Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬। কাজ শুরু ৩ নভেম্বর; baseline `v0.5.0 / c3ed158dcf128e657962d66e3197cc1ade6fee38`।

## আগের gap-এর অর্থ

আগের একই workflow-এ native/Stock total medians ছিল HD 9.4152/9.3138s এবং live-action 7.9022/7.4354s: যথাক্রমে +1.09% ও +6.28%। পাঁচ-pair 95% intervals ছিল 0.9199–1.1069 ও 0.9664–1.1173। উভয় interval equality পার করে; এগুলো স্থায়ী native C regression-এর প্রমাণ নয়। আগের encode medians ছিল HD 7.6683/7.6047s এবং live-action 6.2049/5.8177s। Capability lookup মাত্র 2–3ms; সেখানে কয়েক microsecond বাঁচিয়ে এই gap দূর করা যেত না।

Source, encoder, options, full decode, integrity check ও atomic publish একই contract-এ রেখে bottleneck খোঁজা হয়েছে। Native binary-কে Stock path দিয়ে প্রতিস্থাপন করা হয়নি।

## যেটি যাচাই হয়েছে

- Cold library closure-এ Native ও Stock একই `/opt/homebrew/Cellar/x264/r3222/lib/libx264.165.dylib` নেয়। SHA-256 `dd765b37f50d44d3ce9593c2c1c2424b48bedac01c7999e93cef87e018bc65b4`। Native 38টি ও Stock-এর captured library bindings `initial-bindings.json`-এ retained।
- Actual native `ffbuild/config.mak`-এ `/usr/bin/clang`, `-mcpu=apple-m4`, `-O3`, এবং enabled NEON আছে। Missing `-O3` বা generic CPU build পাওয়া যায়নি। নতুন compiler flags, unsafe floating-point mode বা অপ্রমাণিত rebuild যোগ হয়নি।
- চার owned encoder-এর 3s, 5ms-interval sampled warmup নেওয়া হয়েছে: HD/ToS × Native/Stock। Registered PID, worker PID ও kernel birth identity মিলে sampler attach হয়েছে। এই চার timing measured trials থেকে বাদ।
- চার sample-এই `libx264.165.dylib`-এর NEON routines পাওয়া গেছে: SAD, quantization, interpolation এবং frame analysis। Thread condition/mutex waits-ও দুটিতেই আছে। All-thread stack counts-কে CPU utilisation বা process সময়ের শতাংশ ধরা হয়নি; এই sample দিয়ে thermal throttling বা নির্দিষ্ট wait-এর causal শতাংশ নির্ণয় করা যায় না।
- আগের typed API encoder/validation সর্বোচ্চ ৪ threads নিতে পারত। Long native geometry profile-এর encoder/decoder/filter/audio nominal budget ছিল `4+2+2+1=9`, সর্বোচ্চ অনুমোদিত ১৪-এর মধ্যে। ৮-thread encoder-এ `8+2+2+1=13`; validation অন্য phase-এ আলাদাভাবে চলে। এটি nominal pool accounting, exact OS thread-count ceiling নয়; library lookahead/guardian threads আলাদা।

## Calibration ও নির্বাচনের নিয়ম

একই retained publisher source-এর 60–120s range: BBB 1920×1080/30 এবং Tears of Steel 1920×800/24। ToS-কে 1080-height বলা হয়নি। Source SHA, publisher provenance ও licences আগের corpus receipts-এ আছে।

সাত configuration: Native 4/2/2/4, 6/2/2/4, 8/2/2/4, 8/1/1/4, 8/2/2/8; Stock 4/2/2/4 ও 8/2/2/4। প্রতি source/configuration একটি excluded warmup ও তিন measured trial: 56 actual complete jobs। Seeded sequential order; driver নিজের process niceness অন্তত 10 করেছে, যাতে `jpo`-র expected batch priority policy সব comparator-এ প্রথম থেকেই সমান হয়। অন্য apps/services-এর priority বদলানো হয়নি।

সর্বনিম্ন median এবং quality-pass candidate **8/2/2/8**: calibration HD 8.9571→6.2765s, ToS 7.6507→4.7655s। Encode ও validation দুটিই মাপা হয়েছে। Validation pool বদলানোর সঙ্গে আলাদা trial-এ encode সময়ের পার্থক্যকে validation-এর causal gain বলা হয়নি; independent confirmation প্রয়োজন।

Full-frame quality-তে HD 1,800 এবং ToS 1,440 reference-aligned frames। পূর্বঘোষিত gates: ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05dB, ΔSSIM≥−0.00001, size≤1.02×। নতুন candidate-এর deltas HD +0.020343/+0.004890/+0.000001; ToS +0.004048/+0.000316/+0.000002। Size +0.161574%/+0.024306%। CRF, preset, scaler, audio options ও validation contract বদলায়নি।

৬ ও ৮ threads-এর output নতুন all-frame measurement পেয়েছে। Existing metrics কেবল exact encoded SHA, reference source SHA, range, frame rate, frame count ও metric contents মিলে reuse হয়েছে। সব trials deterministic per-configuration output দিয়েছে। Native ও Stock একই thread settings-এ bit-identical output দিয়েছে।

## Promotion-এর সীমা

`m4_max_hd_software` profile কেবল Apple M4 Max/Darwin arm64, ≥60s, 1920-wide native geometry/height≤1080, progressive square-pixel unrotated 8-bit 4:2:0 H.264/VP8, explicit native integer CFR≤30, software decode/filter, quality mode-এর জন্য। HDR tone map, explicit bitrate, checkpoint, resize/UHD এবং caller pool overrides এই নতুন auto profile নেয় না। পুরোনো calibrated/conservative behaviour থাকে।

Explicit software transcode-এ encoder 1–8 ও validation 1–8; decoder/filter 1–4 এবং total codec/filter/audio budget ১৪ অপরিবর্তিত। `threads>4`-এ explicit `encoder=software` ও যথেষ্ট ছোট decoder/filter pools প্রয়োজন; over-budget request refuse হয়। Hardware ও অন্য operation-এ বড় encoder pool refused।

Calibration-এর পরে আলাদা নয়-pair confirmation: frozen 0.5.0 Native/Stock preset, candidate Native এবং একই নতুন auto tuning-এ Stock control। প্রতি source/configuration নতুন excluded warmup। Ratio of medians-এর 20,000 paired trial-block bootstrap draws; নতুন native-কে পুরোনো native এবং পুরোনো Stock দুটির চেয়ে faster median ও 95% upper ratio<1 হতে হবে। Matched new Stock control-এর ফলও প্রকাশ করতে হবে। অনিশ্চিত বা সমান core performance-কে native superiority বলা হবে না।

## Confirmation-এর HD gap-এর পরের isolation

Independent confirmation-এ একই নতুন tuning-এ HD native/Stock median ratio 1.095348, interval 0.979218–1.315438। এরপর BBB 60–90s-এর 900 decoded frames-এর একটি 2,799,360,000-byte raw reference retained হয়েছে। Stock-এর independently decoded raw SHA-256-এর সঙ্গে native-generated reference হুবহু মিলে। এটি নতুন quality preset নয়; producer/encoder/audio/mux আলাদা করার diagnostic।

চার stage, দুই engine, একটি excluded warmup ও পাঁচ measured adjacent pair: 48 supervised stages। Engine order পালাক্রমে বদলেছে; niceness 10, sequential host lock ও সব বিদ্যমান job/disk/deadline guards বহাল। Native/Stock-এর same-stage encoded output SHA-ও মিলেছে।

| Stage | Native/Stock median ratio | Paired 95% interval | ব্যাখ্যা |
|---|---:|---:|---|
| Compressed source decode/filter | 0.957505 | 0.885995–0.989850 | Native 4.25% দ্রুত, একই decoded pixels |
| Raw reference → x264 | 1.044415 | 1.001246–1.107448 | Native 4.44% ধীর; raw I/O/feed control-এর সীমিত ফল |
| Compressed source → video-only | 0.995496 | 0.761272–1.055760 | Interval equality পার করে |
| Compressed source → video+audio | 1.011890 | 0.950961–1.095421 | Median 1.19% ধীর; 9.5% stable defect পুনরাবৃত্ত নয় |

এই adjacent compressed-source test একটি নির্দিষ্ট 9.5% C regression স্থানীয়করণ করেনি। একই x264 library ও pixels থাকলেও raw feed-এ সামান্য difference আছে; সেটিকে hidden fix বা zero gap বলা হয়নি। Raw I/O, page cache ও host scheduling-এর নির্দিষ্ট causal অংশ মাপা হয়নি। Whole-workflow nine-pair result অক্ষুণ্ণ; ছোট isolation study দিয়ে সেটি প্রতিস্থাপন বা failed trial বাদ দেওয়া হয়নি। নতুন source/build change করার জন্য missing compiler flag বা repeatable compressed-path defect পাওয়া যায়নি।

Isolation receipt `<LAB_ROOT>/ffmpeg-v2-phase8/isolation-20261103T182305-6a8a3972/isolation.json`। Raw control retained; অতিরিক্ত scratch estimate 4GiB, real raw reference 2.61GiB; boot disk-এ রাখা হয়নি।

## প্রাথমিক সূত্র ও স্থানীয় authority

- [FFmpeg libx264 documentation](https://ffmpeg.org/ffmpeg-codecs.html#libx264_002c-libx264rgb): encoding `threads`, frame/slice threading ও CRF পৃথক controls। Sampled local binary/argv নির্ধারণ করে এই workload কী চালিয়েছে।
- [Clang code-generation documentation](https://clang.llvm.org/docs/UsersManual.html#controlling-code-generation): compiler controls; এই candidate-এর actual flags-এর authority retained local `ffbuild/config.mak`।
- Local experiment: `<LAB_ROOT>/ffmpeg-v2-phase8/calibrate-20261103T180018-a55648e2/{report,quality,analysis}.json` এবং ওই directory-র চার `.sample.txt`।
- Initial bindings: `<LAB_ROOT>/ffmpeg-v2-phase8/initial-bindings.json`। প্রথম unsupported ৮-thread baseline attempt media চালানোর আগেই refused; failed report retained।

কাজ sequential; scoped owner RAM waiver receipt-এ আছে। Sampled 12GiB job, disk/mount/output/deadline safeguards বহাল। নতুন কাজের storage `<LAB_ROOT>/ffmpeg-v2-phase8`-এ; T7 originals বা unrelated applications বদলানো হয়নি। Calibration থেকে universal codec/hardware/camera quality বা native algorithm speedup দাবি করা যায় না।
