> ঐতিহাসিক local0.6 build-এর Bangla notes। নতুন public setup-এর জন্য [README](README.md) ও [Getting started](docs/GETTING-STARTED.md) দেখুন। Paths redacted; local installation/benchmark acceptance নতুন computer-এ প্রযোজ্য নয়।

# FFmpeg-v2

**Jillur Rahman**-এর Apple M4 Max computer-এর জন্য enhanced FFmpeg fork, typed JSON CLI ও stdio MCP। Phase 8-এর local release **0.6.0** installed; stable 0.5.0 rollback-এর জন্য retained। Python 3.9+; workflow-এ অতিরিক্ত runtime package লাগে না।

Native core `n9.0.2-3-gb6e0de6-ffmpeg-v2-m4`-এ JSONL progress, optional Metal runtime compilation ও cleanup crash fix আছে। Retained build-এ private zimg/libass, SDL2 ffplay এবং 38 binary/non-system library binding আছে। Processing-এর উন্নতি workflow/thread tuning থেকে আসে; নতুন compression algorithm দাবি করা হয় না। [বর্তমান অবস্থা](STATUS.md), [acceptance register](PHASE8.md), [validation](docs/VALIDATION.md), [contracts](docs/PHASE5-7-DESIGN.md), [source/licence](THIRD_PARTY_NOTICES.md)।

## ব্যবহার

~~~sh
ffv2 --version
ffv2 release status
ffv2 doctor
ffmpeg-v2 -hide_banner -version
ffprobe-v2 -hide_banner -version
ffplay-v2 -version
ffv2 probe '/absolute/path/input.mp4'
ffv2 plan '/absolute/path/job.json'
ffv2 submit '/absolute/path/job.json' --key export-001
ffv2 worker --drain
ffv2 status JOB_ID --events
~~~

`ffv2` plan/queue/watchdog/full validation চালায়। `ffmpeg-v2`/`ffprobe-v2`/`ffplay-v2` pinned native programs-এর পূর্ণ CLI; সরাসরি native command-এর lifecycle caller পরিচালনা করে। Existing trusted program-এ pinned PATH ও supervision দিতে:

~~~sh
ffv2 exec --work-dir '<LAB_ROOT>/my-export' --timeout 1800 -- python3 '/absolute/path/export_worker.py'
~~~

Output project অথবা mounted `<LAB_ROOT>`-এ দিন; directory আগে তৈরি করুন। Source/existing output overwrite হয় না। `completed` receipt-এর metadata, complete strict decode ও output SHA-256 মিলে তবেই result ব্যবহার করুন। [দৈনন্দিন workflow, update ও recovery](docs/OPERATIONS.md)।

## নয়টি typed operation

| Operation | ফল |
|---|---|
| `transcode` | প্রথম A/V থেকে H.264/AAC MP4; software/VideoToolbox, VFR অথবা explicit CFR; bounded CFR checkpoint option |
| `audio` | নির্দিষ্ট range-এর PCM s16le WAV, mono/stereo ও নির্দিষ্ট sample rate |
| `frame` | Requested time-এর at/after decoded frame, actual source PTS receipt |
| `contact_sheet` | 2–64 sample-এর JPEG grid; dense pass অথবা count≤8 bounded sparse seeks, actual PTS |
| `remux` | সব stream Matroska-তে copy; decoded trim নয় |
| `concat` | Compatible ordered stream-copy Matroska অথবা bounded normalized CFR/audio join |
| `subtitle` | Verified local SRT/ASS/SSA ও font দিয়ে subtitle burn-in; বাংলা font preset |
| `audio_mix` | Primary ও সর্বোচ্চ 7 extra track, gain/offset/loop/normalization/limiter, sample-accurate WAV |
| `image` | Still PNG/JPEG/WebP থেকে PNG/JPEG; alpha/matte, odd dimensions ও 8/16-bit PNG |

[Examples](examples/) নিজের absolute paths দিয়ে ব্যবহার করুন। Unknown fields, arbitrary argv/filtergraph, nonfinite values, unsupported combinations ও overwrite attempts refuse হয়। Subtitle/font/mix inputs-ও source bindings এবং MCP read-root policy মেনে চলে।

Explicit quality mode software encoder নেয়; unsupported hardware quality request নীরবে উপেক্ষা হয় না। Hardware decode actual hardware surfaces দিয়ে পরীক্ষা হয়; no-silent-fallback policy থাকে। `filter_backend=videotoolbox` opt-in: দীর্ঘ 4K calibration-এও quality regression হওয়ায় default `software` রাখা হয়েছে।

Long 8-bit progressive software clips-এর উপযুক্ত M4 Max profile-এ decoder/encoder/filter/validation pools আলাদা করে calibrate করা হয়েছে। Phase 8-এর matching HD native-geometry quality profile-এ pools 8/2/2/8; nominal encode budget ১৩, সীমা ১৪। Explicit pools, 4K/resize ও অন্য presets আগের behaviour নেয়। [Eligibility ও diagnostics](docs/PHASE8-RESEARCH.md), [software HD example](examples/transcode-software-hd.json)।

নতুন auto tuning `ffv2` typed jobs ও MCP-এর জন্য। Example-এ নিজের paths ও native source fps দিন; pool fields বাদ রাখুন। সরাসরি `ffmpeg-v2` পূর্ণ native CLI চালায়; তার codec/thread options caller নির্ধারণ করে।

## HDR, colour ও recovery

Static known PQ/HLG-এর tone map-এ `hdr_policy=tone_map` এবং caller-জানা `source_peak_nits` প্রয়োজন। Supported colour metadata ছাড়া `hdr_metadata_required`; dynamic HDR/Dolby Vision refuse। Video SDR output BT.709 limited; HDR image preset full-range 16-bit sRGB PNG দেয়। Filename থেকে colour অনুমান হয় না। [বিস্তারিত contract](docs/PHASE5-7-DESIGN.md)।

`checkpoint_seconds=5..600` zero-origin CFR source ও একই explicit integer fps চায়। Validated video segments ও একটি continuous AAC pass source/spec/code/engine hashes মিলে retry-তে reuse হয়। Corruption হলে সংশ্লিষ্ট segment rebuild হয়। Higher-priority কাজ থাকলে durable boundary-তে yield করা যায়। VFR/nonzero-origin source সাধারণ transcode-এ supported; checkpoint preset-এ নয়।

~~~sh
ffv2 cancel JOB_ID
ffv2 retry JOB_ID
ffv2 worker --job-id JOB_ID
~~~

Independent guardian worker/supervisor loss-এর সময় owned process group থামায়। Publish-intent validated post-link/database-loss recovery দেয়। Resource trace durable; receipts ও successful/partial files retained। Sampling ও user-space watchdog OS/kernel failure-এর universal guarantee নয়।

## MCP

~~~sh
ffv2 --input-root '/absolute/path/media-root' mcp
~~~

8 tools: doctor, probe, plan, submit, worker_start, job_status, job_cancel, job_retry। Submit queue করে; worker start আলাদা action। Default server startup কাজ শুরু করে না। [MCP contract](docs/MCP.md) ও [generic configuration](examples/mcp.config.json)। Client configuration, fresh stdio round trip এবং বর্তমানে খোলা chat-এর hot reload আলাদা প্রমাণ।

## Install/update/rollback

Frozen release code ও engine snapshot আলাদা directory-তে থাকে; একটি atomic pointer দিয়ে pair নির্বাচন হয়। Queue/state project-এ থাকে। দশটি acceptance gate ও matching hashes ছাড়া install হয় না। Queued/running কাজ থাকলে update refuse করে; previous release retained থাকে।

~~~sh
ffv2 release status
ffv2 release install --source '/absolute/verified/source' --acceptance '/absolute/completed-acceptance.json'
ffv2 release rollback
~~~

Update-এর পরে পুরোনো connection-এ `release_changed` হলে নতুন MCP connection নিন। `runtime_code_changed` হলে পুরোনো checkpoint-এর matching release-এ rollback করে retry করুন, অথবা নতুন plan দিন। [Operational guide](docs/OPERATIONS.md) ও [native build/update](docs/UPSTREAM.md)। System/Homebrew `ffmpeg` replace হয় না।

## মাপা ফল ও যাচাই

Phase 8-এর নতুন নয়-pair confirmation-এ পুরোনো Stock preset-এর তুলনায় HD/live-action workflow সময় **22.61%/28.48% কম**, পুরোনো Native-এর তুলনায় **22.31%/30.77% কম**। Full-frame quality ও size gates pass। একই নতুন tuning-এ Stock control-ও প্রকাশিত: HD native median +9.53%, ToS −0.84%; উভয় interval equality পার করে। Native core-এর universal speed advantage প্রমাণিত নয়। [সম্পূর্ণ comparison](docs/PHASE8-RESULTS.md), [portable index](docs/verification/phase8-2026-11-04.json), [register](PHASE8.md)।

Phase 9-এ HD/raw gap-এর controlled diagnostics, actual x264/feed probe, scheduler queue candidate ও lookahead candidate পরীক্ষা করা হয়েছে। Lookahead-এর calibration gain independent complete workflow-এ টেকেনি; quality pass করলেও candidate 39.94% ধীর হয়েছে। কোনো নতুন performance default বা release গৃহীত হয়নি; verified 0.6.0 বহাল। [Phase 9 comparison](docs/PHASE9-RESULTS.md), [research](docs/PHASE9-RESEARCH.md), [অসম্পন্ন performance gates](PHASE9.md)।

Phase 10-এর private x264 candidate-এ progress-query lock traffic প্রায় 98.4% কমেছে এবং একই target content encode করতে active Native-এর চেয়ে 2.9–3.3% কম instructions লেগেছে। HD/raw video ও HD audio-এর decoded frame SHA-256 exact match। Controlled added-load ও per-worker/process profiling CPU queue এবং raw file-cache imbalance দেখিয়েছে। 180 encode + 45 full-workflow run-এর wall-clock confidence gate pass হয়নি; candidate experimental, installed 0.6.0 বহাল। [Phase 10 ফল](docs/PHASE10-RESULTS.md), [method](docs/PHASE10-RESEARCH.md), [source patches](third_party/x264/README.md), [evidence](docs/verification/phase10-2026-11-04.json)।

দীর্ঘ বাস্তব 1080p/4K animation ও 1920×800 live-action/VFX corpus-এর আগের [Phase 4 ফল](docs/PHASE4-RESULTS.md), [Phase 4–7 acceptance](docs/PHASE4-7-RESULTS.md), [পুরোনো index](docs/verification/phase4-7-2026-11-03.json) ও [register](PHASE4-7.md) retained। সেখানে rejected hardware scaler, broader workflows, long run ও compatibility-এর original scope আছে।

Historical [Phase 2](docs/PHASE2-RESULTS.md) ও [Phase 3](docs/PHASE3-RESULTS.md) ফল সংরক্ষিত। Phase 2-এর software pipeline native +9.26% slowdown historical; Phase 3-তে একই engine-এর pipeline 21.44% এবং actual CLI process 17.75% কম সময় নিয়েছিল। এগুলো short fixtures-এর আলাদা epochs; নতুন দীর্ঘ-workload ফলের সঙ্গে এক measurement হিসেবে মেশানো হয় না।

~~~sh
python3 -B scripts/verify_unit_matrix.py
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_phase5.py --prefix '/absolute/native/prefix'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_phase6.py --prefix '/absolute/native/prefix' --mode quick --source '/absolute/retained-real-cfr.mkv'
~~~

Released 0.6.0-এর দুই Python runtime-এ **131টি করে control test**। Phase 9 source-এ ৫টি benchmark-analysis test-সহ Python 3.9/3.14-এ **136টি করে pass**, এবং fresh configured installed MCP checks pass। Native base/extended, advanced workflow, real Studio consumer, 30-minute elapsed soak, long real batch, broader formats ও selected external FATE-এর original bounded proof আছে; Phase 8-এর fresh source/installed checks আলাদা index-এ। Full external suite, overnight reliability, every camera/codec, perceptual HDR mastering, cross-platform calibration ও public distribution-এর universal acceptance দাবি নেই। [Known gaps](docs/GAPS.md)।

Phase 10 source-এর দুই runtime-এ **142টি করে test**; private candidate-এর fresh native CLI/MCP/media 14 checks এবং ছয়টি codec-mode regression pass। Target frame identity ও ThreadSanitizer-এর bounded scope Phase 10 report-এ আছে; full release lifecycle এই experimental candidate-এর জন্য accepted নয়।

Phase 11-এর bounded evaluation শেষ: private no-LTO PGO candidate-এর complete1080p workflow-এ Stock-এর তুলনায় **1.743%/1.791% কম elapsed time**, দুই controlled-load state-এ9 valid blocks করে; quality/decoded video+audio exact। Encoder-only HD-এ1/9 করে এবং raw-এ3/9 ও7/9 valid block হওয়ায় overall release gate fail; candidate experimental, default original0.6.0 বহাল। Native14, six codec modes ও দুই runtime-এ **176টি করে test** pass। Device-ID drift-এর পরে exact original0.6/retained0.5 package metadata reverified; actual rollback এবং installed CLI/MCP pass। [পূর্ণ Phase 11 comparison](docs/PHASE11-RESULTS.md), [cold index](docs/verification/phase11-2026-11-05.json), [method](docs/PHASE11-RESEARCH.md), [register](PHASE11.md), [PGO provenance](third_party/x264/phase11-pgo.json)।

Owner-এর explicit RAM waiver-এ task runs-এ `--ignore-system-memory` অথবা `FFV2_IGNORE_SYSTEM_MEMORY=1` ব্যবহৃত হয়েছে। এটি শুধু সেই invocation/worker-এর pressure/headroom/swap stop উপেক্ষা করে। Default policy, sampled 12 GiB job footprint, disk/mount/time/output checks ও sequential heavy-work policy বহাল থাকে; unrelated apps বন্ধ করা হয় না।
