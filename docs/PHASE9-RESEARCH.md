# Phase 9: HD/raw gap-এর নিয়ন্ত্রিত অনুসন্ধান

৪ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Frozen baseline `v0.6.0 / a8e44c8a725eb20279072654e5f5a35b7e961a8e`; native `b6e0de6e580ae325d5b12df79dddd364ccf11efb`। Active release candidate-এর acceptance-এর আগে বদলাবে না।

## পুনরাবৃত্তি ও পরিবর্তনশীল computer state

আগের +9.53% HD এবং +4.44% raw ফল retained। একই argv, source SHA, binaries ও shared library closure-তে নতুন ABBA/BAAB run-এ HD +8.26%, raw −1.27%। HD-তে instructions ratio 0.99166, CPU cycles 0.99708, user+system time 0.99816; wall ratio 1.08260। কাজের পরিমাণ প্রায় সমান থাকা সত্ত্বেও elapsed time আলাদা হয়েছে।

পরের epoch-এ কোনো product/native পরিবর্তন ছাড়াই HD baseline ratio 0.92594। একই HD work-এর CPU time প্রায় 40.9s থেকে 28.5s হয়েছে। এটি host execution/scheduling state-এর সংবেদনশীলতা প্রতিষ্ঠা করে; নির্দিষ্ট thermal, clock বা অন্য application-এর causal শতাংশ মাপা হয়নি। ভিন্ন epoch-এর দ্রুততম ফল একত্র করে speedup বলা যাবে না।

প্রতি block-এ `Native,Stock,Stock,Native` অথবা উল্টো order; initial warmups excluded, সব পরের slow run retained। `/usr/bin/time -lp`-তে বাস্তব elapsed/user/system time, retired instructions, cycles, faults ও context switches নেওয়া হয়েছে। Whole adjacent block resample করা হয়; একই block-এর চার observation-কে চার independent experiment ধরা হয় না। Calibration এবং independent confirmation আলাদা।

## Actual encoder ও feed

দুই engine একই `/opt/homebrew/Cellar/x264/r3222/lib/libx264.165.dylib` ব্যবহার করে, SHA-256 `dd765b37f50d44d3ce9593c2c1c2424b48bedac01c7999e93cef87e018bc65b4`। Excluded interposition probe actual encoder open এবং প্রথম তিনটি picture দেখেছে; প্রতিটি probed output uninstrumented reference-এর exact SHA দিয়েছে।

| পরিমাপ | Native | Stock |
|---|---:|---:|
| x264 frame threads | 8 | 8 |
| Lookahead threads | 2 | 2 |
| Synchronous lookahead depth | 4 | 4 |
| Rate-control lookahead | 10 | 10 |
| CPU dispatch flags | 202 | 202 |
| Encoder worker QoS / scheduling priority | 21 / 31 | 21 / 31 |
| Picture strides | 1920 / 960 / 960 | 1920 / 960 / 960 |
| Plane-address modulo 128 | 0 / 0 / 0 | 0 / 0 / 0 |
| HD observed x264-created threads | 11 | 11 |

ভিন্ন x264 defaults, CPU dispatch, প্রাথমিক plane alignment বা worker QoS gap-এর ব্যাখ্যা দেয়নি। Nominal `8+2+2+1=13` pool budget exact OS thread ceiling নয়; x264-এর lookahead ও scheduler threads আলাদা। Native-তে প্রায় ৮১টি অতিরিক্ত startup page fault ছিল; সেগুলোর elapsed cost মাপা ছাড়া 9.53% regression-এর কারণ বলা যায় না। Darwin block-I/O counters এখানে শূন্য এসেছে; এটি physical disk activity শূন্য থাকার প্রমাণ নয়।

Probe প্রথমে local SDK-এর `pthread_get_qos_class_np` signature ও loader symbol resolution ভুলভাবে ব্যবহার করেছিল। ওই failed compile/run retained; working probe SDK-এর তিন-argument API এবং direct interposed originals ব্যবহার করে। Product environment allowlist-এ diagnostic loader variables যোগ হয়নি; observer কেবল নিজের explicit trusted child command-এ দেওয়া হয়েছে। কোনো instrumented timing promotion-এ ব্যবহৃত হয়নি।

## বাদ দেওয়া ধারণা

Identity `scale=1920:1080` সরালে bitstream একই ছিল, কিন্তু HD native median 4.911→5.131s হয়েছে; default থেকে scale বাদ দেওয়ার speed evidence নেই। `-nofind_stream_info`-ও একই output দিয়েও HD/raw লাভ দেখায়নি। Input integrity, stream probing, scaler ও strict decode বন্ধ করে speed দাবি করা হবে না।

`-thread_queue_size` local n9 source-এ output mux queue-তে ব্যবহৃত হয়; এটিকে decoder-to-encoder frame-queue control ধরে tuning করা ভুল হবে। Scheduler frame queue default **2**। আলাদা candidate-এ global expert `-frame_queue_size 2..16` দিয়ে queue capacity এবং decoder hardware-pool extra-frame accounting একই bound পায়। Original default 2 retained। Capacity বাড়িয়ে decoder pool না বাড়ালে fixed hardware buffers-এর safety contract ভাঙতে পারে। Queue candidate-এর compile এবং calibration acceptance-এর প্রমাণ নয়।

## সব frame-এর encoder-call timing probe

দ্বিতীয় excluded observer-এ প্রথম তিনটি picture-এর পাশাপাশি প্রতিটি actual encoder input ও flush call গোনা হয়েছে। HD 1,800 এবং raw 900 input; উভয় engine-এ যথাক্রমে 1,823 ও 923 calls। প্রতিটি output আবার uninstrumented baseline-এর exact SHA দিয়েছে। Constructor-এর পরের monotonic wall partitions:

| Workload / engine | First input | x264 call-এর ভেতরে মোট | Call-এর মাঝের মোট | Observed process |
|---|---:|---:|---:|---:|
| HD Native | 0.426441s | 7.406057s | 0.172346s | 8.015805s |
| HD Stock | 0.542265s | 7.998036s | 0.182814s | 8.730363s |
| Raw Native | 0.013711s | 4.708488s | 0.025730s | 4.755577s |
| Raw Stock | 0.007828s | 4.449275s | 0.028382s | 4.490690s |

Raw Native-এর অতিরিক্ত সময় প্রধানত একই x264 implementation-এর call-এর ভেতরে হয়েছে; serialized frame-feed gaps উভয় engine-এ ছোট। এটি এই sample-এ raw read/frame-copy bottleneck-এর সমর্থন দেয়নি। Call-এর wall time-এ encoder worker-এর CPU execution, synchronization ও scheduling wait একসঙ্গে আছে; আলাদা worker CPU accounting ছাড়া সেই অংশগুলোকে causal শতাংশে ভাগ করা যায় না। Parallel producer-এর সম্পূর্ণ I/O cost-ও এই partition দিয়ে মাপা হয়নি। Instrumented timings speed promotion-এর সংখ্যা নয়।

Queue 2/4/8/16 calibration-এর ৮০টি run-এ কোনো capacity দুই workload-এ একসঙ্গে স্থির লাভ দেয়নি। Queue 16 Native/Stock ratios HD 0.997127, raw 0.990820; block intervals যথাক্রমে 0.9455–1.0276 এবং 0.9685–1.0718। Queue 4 HD-তে দ্রুত median দিয়েও raw-তে 31.02% ধীর হয়েছে; সব ধীর run retained। Candidate patch [এখানে](experiments/phase9-frame-queue-capacity.patch); active patch series বা production default-এ নেই।

Lookahead calibration-এ শুধু HD-র Native median-এ `lookahead-threads=1` প্রায় 8.85% কম সময় নিয়েছে; raw-তে লাভ হয়নি। একই দুই-block study-তে HD-র এক block-এ candidate ধীর এবং অন্যটিতে দ্রুত ছিল। তাই এই calibration percentage গ্রহণযোগ্য improvement নয়। [ছোট scoped SDK candidate](experiments/phase9-hd-lookahead.patch) আলাদা checkout-এ; independent full workflow ও নতুন all-frame metrics ছাড়া default হবে না। `sync-lookahead=0`-ও উভয় target-এর candidate হিসেবে নির্বাচিত হয়নি।

## স্থানীয় কর্তৃত্ব ও সূত্র

- Actual local n9 source: `fftools/ffmpeg_sched.c`, `fftools/ffmpeg_dec.c`, `fftools/ffmpeg_opt.c`, `fftools/ffmpeg_demux.c`, `fftools/ffmpeg_mux_init.c`।
- [FFmpeg CLI documentation](https://ffmpeg.org/ffmpeg.html): thread queues ও option placement; installed source-এর actual implementation দিয়ে যাচাই করা হয়েছে।
- [FFmpeg rawvideo documentation](https://ffmpeg.org/ffmpeg-formats.html#rawvideo): headerless raw input-এর explicit geometry/pixel-format/frame-rate contract।
- Apple SDK `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include/pthread/qos.h` এবং actual guarded observer trace।

সব নতুন বড় data mounted `<LAB_ROOT>/ffmpeg-v2-phase9`-এ। Retained raw reference 2,799,360,000 bytes পুনর্ব্যবহৃত। Native candidate ২-job incremental build-এ পুরোনো immutable build cache clone করে; original cache/source/install অপরিবর্তিত। Sampled job limit, output/disk/mount/deadline guards এবং scoped owner memory waiver বহাল।
