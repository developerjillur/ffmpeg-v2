# FFmpeg-v2 Phase 2 — সম্পূর্ণ ফল ও তুলনা

সম্পন্ন: **৩ নভেম্বর ২০২৬**। Maintainer: **Jillur Rahman**। Local workflow release **v0.3.0**। Native engine **n9.0.2-3-gb6e0de6-ffmpeg-v2-m4** activate হয়েছে।

Phase 2-তে workflow startup/query খরচ, sparse sampling, Metal availability/crash, explicit HDR/interlace/decode policy এবং বাস্তব recovery/soak যাচাই সম্পন্ন হয়েছে। ফলগুলো এই Mac ও নিচের workloads-এর local acceptance।

পরীক্ষার host: Apple M4 Max, 36 GiB unified memory, live-verified macOS **27.2**। System তখন অন্য apps/jobs-ও চালাচ্ছিল।

## v0.2.0 থেকে workflow উন্নতি

একই frozen native engine, একই 6s 1280×720/30fps FFV1/PCM source এবং একই output contract। প্রতিটি label/operation-এ একটি excluded warmup এবং ৭টি measured trial; seeded interleaved order। Source SHA-256 `031093afc3b1a23d58fbc44d087ab3d82918caed1fabe1f857dd2e63388acdff`। পুরোনো source checkpoint v0.2.0 / ccc1131; Phase 2 runtime code hashes acceptance index-এ আছে।

| পরীক্ষা | v0.2.0 median | Phase 2 median | পরিবর্তন | অনুপাত |
| --- | ---: | ---: | --- | ---: |
| Software transcode: job pipeline | 1.926707 s | 1.235583 s | 35.87% সময় কম | 1.56× |
| Software transcode: CLI process | 2.019928 s | 1.310163 s | 35.14% সময় কম | 1.54× |
| Dense 16-frame sheet: job pipeline | 1.091256 s | 0.585183 s | 46.38% সময় কম | 1.86× |
| Dense 16-frame sheet: CLI process | 1.193842 s | 0.670658 s | 43.82% সময় কম | 1.78× |

Job pipeline-এর মধ্যে capability lookup, input probe, planning, queue, supervised encode, metadata/full decode, hash ও atomic publish আছে। CLI process-এ Python startup ও process completion-ও মাপা হয়েছে। দুই workflow-এর transcode outputs এবং দুই workflow-এর dense sheets নিজ নিজ operation-এ whole-file SHA-256 অনুযায়ী identical।

মূল পরিবর্তন: verified engine-এর capability cache, execution-এ identity-only plan check এবং encode/validation-এ reusable independent supervisor। Full output validation ও no-clobber publish বহাল। Capability lookup-এর software-case median 0.217764 → 0.001396 s; এটিকে পুরো job-এর speedup বলা হয়নি।

## দীর্ঘ sparse sampling

এই তুলনার **দুই পদ্ধতিই Phase 2-এর একই pipeline/engine**; v0.2.0-versus-v0.3.0 test নয়। 600s source থেকে 8টি target, 75s interval; ৩টি alternating-order trial, warmup বাদ নয়।

| পদ্ধতি | Median job time | ফল |
| --- | ---: | --- |
| সম্পূর্ণ range single-pass decode | 5.982818 s | 8টি verified source PTS |
| Bounded multi-input seek | 0.361135 s | একই 8টি PTS ও decoded pixels |

এই fixture-এ **16.57×**, অর্থাৎ **93.96% সময় কম**। Targets: 0, 75, 150, 225, 300, 375, 450, 525s। Auto heuristic count≤8, progressive source, ≥30s interval ও bounded decoder estimate ব্যবহার করে। Long-GOP বা অন্য source-এ এই ratio নিশ্চিত নয়; `single_pass` explicit override আছে।

## Stock FFmpeg বনাম নতুন native core

দুই engine-এ **একই Phase 2 workflow**, একই source/preset/thread limits ও legacy key/value progress। দুই engine-ই এখানে unselected explicit configuration; persistent selected-engine cache এই comparison-এ নেই। প্রতি case একটি excluded warmup ও ৫টি measured trial। Compiler/configuration এবং storage/load path আলাদা; ফলকে শুধু M4 flags বা কোনো এক C patch-এর causal speedup বলা যায় না।

| পরীক্ষা | Installed 9.0.2 median | Native median | পরিবর্তন |
| --- | ---: | ---: | --- |
| H.264 software: media process | 0.729080 s | 0.682904 s | 6.33% কম সময় |
| H.264 software: job pipeline | 1.464336 s | 1.599936 s | 9.26% বেশি সময় |
| H.264 VideoToolbox: media process | 0.600913 s | 0.512835 s | 14.66% কম সময় |
| H.264 VideoToolbox: job pipeline | 1.429695 s | 1.421567 s | 0.57% কম সময় |
| একই single-pass 16-frame sheet: media process | 0.350354 s | 0.280845 s | 19.84% কম সময় |
| একই single-pass 16-frame sheet: job pipeline | 1.035110 s | 0.917372 s | 11.37% কম সময় |

**Software পূর্ণ job pipeline এই run-এ stock-এর চেয়ে 9.26% ধীর।** Encoding অংশে কম সময় লাগলেও startup/probe/validation ও busy-host variability-সহ পুরো ফলের সীমা আছে। সব workload-এ native core দ্রুত—এমন ফল পাওয়া যায়নি। উপরের v0.2 workflow comparison-এর 35.87%/46.38% improvement পৃথক experiment।

## Compression ও video quality

প্রতি cell-এ installed/native ক্রম। প্রতি engine/encoder-এর একটি retained measured output-এ ঠিক 180 decoded frame ও 30fps frame-number alignment দিয়ে quality মাপা হয়েছে। Timestamp-only 181-frame metric ব্যবহার হয়নি।

| Encoder | Output size installed/native | Native-এর অতিরিক্ত compression | VMAF | SSIM | PSNR-Y dB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Software | 3,082,562 / 3,082,562 B | 0% | 97.521175 / 97.521175 | 0.999420 / 0.999420 | 46.860962 / 46.860962 |
| VideoToolbox | 3,116,893 / 3,116,893 B | 0% | 96.056957 / 96.056957 | 0.998627 / 0.998627 | 44.105382 / 44.105382 |

দুই build-এ tested bitrate/preset-এর file sizes এবং একই encoder-এর video quality metrics সমান। Codec algorithm পরিবর্তন করে বাড়তি compression অর্জনের প্রমাণ নেই। Software ও VideoToolbox-এর quality একে অপরের সমান নয়। AAC perceptual audio-quality benchmark করা হয়নি; PCM exactness ও remux packet preservation পৃথক checks।

## Compatibility ও আচরণ

| বিষয় | Stock | v0.2.0 native/workflow | v0.3.0 native/workflow |
| --- | --- | --- | --- |
| Listed encoders | 193 | 193 | 193; missing stock names: [] |
| Listed filters | 483 | 482 | 484; missing stock names: []; extra zscale |
| ffplay | Build-এ আছে | Build disabled | Build + launcher + headless dummy playback pass |
| yadif_videotoolbox | এই পরীক্ষায় cleanup SIGSEGV | Missing offline compiler-এর জন্য বাদ | Runtime compiler + ownership fix; NV12/P010 GPU pass |
| Native JSONL progress | নেই | আছে | আছে; default kv বহাল |
| HDR typed transcode | Raw CLI caller policy | Refusal | Explicit known PQ/HLG→BT.709 SDR |
| Interlaced typed input | Raw CLI caller policy | Refusal | Explicit bwdif send_frame |
| Explicit hardware decode | Caller-নিয়ন্ত্রিত | Flag ছিল; surface proof সীমিত | Forced hardware frames/hwdownload; silent fallback refusal |
| VFR contract | Caller-নিয়ন্ত্রিত | Broad corpus proof ছিল না | 60-frame PTS preservation pass |
| Sparse sheet | Raw select/seek options আছে | Single-pass | Auto/single_pass/seek, count≤8 bounded seek |

NV12 ও P010-তে stock-এর per-packet-flushed **60টি complete frame hash** native-এর সঙ্গে মিলেছে। Stock process cleanup-এ exit -11; native exit 0। Stock-এর failed exit-কে successful process বা valid published output ধরা হয়নি। Crash trace ও Apple SDK ownership declaration অনুযায়ী native patch per-dispatch autorelease pool ব্যবহার করে।

## Real acceptance matrix

| পরীক্ষা | ফল ও সীমা |
| --- | --- |
| Control/regression | 80 tests; Python 3.9.6 ও 3.14.7 pass |
| Local FATE | 2,893 records; 0 failures; 2,894 targets listed; default-run hwdevice record আলাদা |
| Base native acceptance | 14 checks; nonzero audio, H.264 software/VT, frame/sheet PTS, remux packets, progress, MCP ও ffplay |
| Extended acceptance | 21 checks; candidate/version/checksum-bound reports |
| HDR | PQ ও HLG tagged 10-bit lossless fixture; correct BT.709 tags ও full decode |
| Analytic PQ ramp | ST2084/Hable/BT1886 formulas; max error **0.381 luma level (8-bit 0–255 scale)**; known neutral 0–1000nit ramp |
| VFR/rotation | 60-frame PTS preservation; 90° rotation 96×128 output |
| Corruption/network playlist | Refused; invalid output publish হয়নি |
| Natural footage | Akiyo 300 frames, Bus 75 frames; counts/full decode pass; QCIF functional corpus |
| 4K SDR Main10 | Hardware p010 download, typed HW decode/encode, 1080p export, metadata/bit-depth-preserving remux; source unchanged |
| Worker SIGKILL | Independent supervisor owned FFmpeg থামিয়েছে; host lock released; recovery receipt আছে |
| Running cancel/timeout | Owned child gone; stop reasons/receipts retained; lock released |
| Real-time GPU soak | 90s media; **89.549s wall time**, 88 resource samples; full decode pass |
| Soak sampled footprint | Peak **194.53 MiB**; after 10s observed range 194.25–194.52 MiB; 18 trace points |
| Runtime provenance | 30 binary/non-system dylib files; media proof-এর আগে/পরে ও activation-এ same closure |
| Source replay | তিন checksum-verified patch pinned base-এ temporary index দিয়ে replay; tree 9aa217e95f59d602a50b4360c0835fdfcf9c1521 matches |

Footprint একটি job/controller group-এর sampled measurement; baseline RAM savings, GPU-wide allocation quota, energy efficiency বা overnight leak-freedom-এর প্রমাণ নয়। Full external-sample FATE, natural HDR display/colour-volume acceptance ও private HD camera corpus এখনও পৃথক scope।

## Resource ও release state

Owner-এর RAM/pressure override এই task-এর invocation-এ scoped ছিল; per-job footprint, mounted volumes, boot-disk 400GB ceiling, output budget ও timeout checks বহাল। এক build FATE চলাকালে boot disk 400GB ছোঁয়ায় থেমেছিল; saved compile checkpoint ও recovered headroom দিয়ে resume হয়েছে। শেষ native ownership-fix candidate fresh configure/build/GPU-smoke/FATE-এ pass করেছে। কোনো unrelated app/service বন্ধ করা হয়নি।

Active native source head `b6e0de6e580ae325d5b12df79dddd364ccf11efb`; workflow version v0.3.0। Old active selection ও successful outputs retained। User-local ffv2/ffmpeg-v2/ffprobe-v2/ffplay-v2 আছে। Local MCP round trip verified; current chat hot reload বা production context-worker migration-এর acceptance আলাদা। Public push/hosted release হয়নি।

Open priorities: software pipeline startup/validation cost, broader real HD/HDR corpus, typed subtitle/concat/filter contracts, all-preset zero-copy scaling, priority/preemption, production migration এবং supervisor নিজে SIGKILL হলে kernel guarantee। [Known gaps](GAPS.md) বর্তমান সীমা ধরে রাখে।

## Raw evidence

- [Portable acceptance receipt](verification/phase2-2026-11-03.json)
- [Workflow benchmark](<LAB_ROOT>/ffmpeg-v2-phase2/benchmark-workflow-20261102T180243-df15c019/report.json)
- [Matched core benchmark](<LAB_ROOT>/ffmpeg-v2-phase2/benchmark-core-20261102T180441-2a20e025/report.json)
- [Native acceptance](<<PROJECT>/.runtime/verification/native-media-20261102T175014-a13e42c5/report.json>)
- [phase2-media-20261102T175513-1423eed3](<<PROJECT>/.runtime/verification/phase2-media-20261102T175513-1423eed3/report.json>) — SHA-256 `06096ba619168a1f5a8558c1280a33187a8d0fd4dcc49c36410f90d841ec1596`
- [phase2-natural-20261102T175524-d01d544e](<<PROJECT>/.runtime/verification/phase2-natural-20261102T175524-d01d544e/report.json>) — SHA-256 `ea8204c83dd2f1194d64d461a3d7b0c8588942b5bdb2f8bf354b0a2d9176396f`
- [phase2-sparse-20261102T175944-2224f196](<<PROJECT>/.runtime/verification/phase2-sparse-20261102T175944-2224f196/report.json>) — SHA-256 `5bad36701bf0dcef80ab35fca78838f0110029ee3cf5f5fc4cc25b5baecdd99c`
- [phase2-large-20261102T175813-f03bc55c](<<PROJECT>/.runtime/verification/phase2-large-20261102T175813-f03bc55c/report.json>) — SHA-256 `dd27fef556429a1acb70dc28fb84b8df4ab7febd893a1b4d3c8981349812b289`
- [phase2-faults-20261102T175918-6cd42310](<<PROJECT>/.runtime/verification/phase2-faults-20261102T175918-6cd42310/report.json>) — SHA-256 `341fc6c34d1054871dada96cf5d5fccead177e38f9ef3ee77231e446ad2fed86`
- [phase2-soak-20261102T180054-d93da95d](<<PROJECT>/.runtime/verification/phase2-soak-20261102T180054-d93da95d/report.json>) — SHA-256 `a428d63f765b1ed8aa7bf0c5880d4f7b6a1033f5a2c88cba5254819dbd9e8f6e`
- [mcp-pipeline-20261102T180039-1cb2a39e](<<PROJECT>/.runtime/verification/mcp-pipeline-20261102T180039-1cb2a39e/report.json>) — SHA-256 `7eb0b853bf6158e8e20ca5983be87e4ef5000094b15ae0fb166477985cfff589`
