# Phase 5–7: workflow, recovery ও release contract

Maintainer: **Jillur Rahman**। ৩ নভেম্বর ২০২৬। বাস্তব ফল ও lifecycle-এর শেষ gate [acceptance register](../PHASE4-7.md)-এ আছে। এই নথি implementation-এর contract ব্যাখ্যা করে; প্রতিটি supported combination পরীক্ষা হয়েছে এমন দাবি করে না।

## Typed media workflows

CLI ও MCP একই strict schema নেয়। Unknown field, nonfinite value, অতিরিক্ত nesting, raw argv/filtergraph ও allowlist-এর বাইরের input প্রত্যাখ্যাত হয়। Media-এর পাশাপাশি subtitle, font ও mix track-এর identity plan-এ বাঁধা থাকে; preparation, encode ও publish-এর সময় আবার পরীক্ষা হয়। সব operation staged output-এর metadata, full decode ও SHA-256 যাচাই করে existing file overwrite ছাড়াই publish করে।

Symlink resolve করার পরে canonical input/output/state path-এ newline/CR-ও refuse হয়। শুধু caller-এর raw path পরীক্ষা যথেষ্ট নয়: alias-এর target-এর নাম concat manifest-এর line contract ভাঙতে পারে। Regression-এ সাধারণ alias দিয়ে hidden newline/CR input, output directory ও state directory—তিনটি route পরীক্ষা হয়; fresh MCP-তেও input/output refusal আছে।

| Operation | Contract | Explicit সীমা |
|---|---|---|
| `concat` / `copy` | Ordered codec/extradata/timebase/geometry/colour signature মিলে সব stream Matroska-তে copy | Mismatched clips refuse; exact trim বা arbitrary edit নয় |
| `concat` / `normalize` | সর্বোচ্চ ৮ input; নির্দিষ্ট CFR, geometry ও audio rate/channel-এ decode/join | Missing audio-তে silence; mixed colour contract-এর আগে explicit preparation দরকার |
| `subtitle` | UTF-8/UTF-16 SRT অথবা ASS/SSA; cue timing, range ও offset; verified local font | সর্বোচ্চ ১ MiB, ১০,০০০ cue ও প্রতি cue ৮,১৯২ character; embedded font/graphics unsupported |
| `audio_mix` | Primary plus সর্বোচ্চ ৭ track; gain, offset, audio loop, normalization ও limiter; PCM WAV | Sample-accurate duration; loop করার video আগে audio হিসেবে extract করতে হবে |
| `image` | Still PNG/JPEG/WebP input; PNG/JPEG output, resize, alpha/matte ও 8/16-bit PNG | Animated PNG/WebP refuse; JPEG 8-bit; HDR alpha unsupported |

`subtitle_font=bengali` এই computer-এর hash-verified Bangla Sangam MN ব্যবহার করে। Font source-এর private copy ছাড়া arbitrary filtergraph-এ path বসানো হয় না। বাংলা cue-এর visible timing ও glyph preview পরীক্ষা হয়েছে; সব font বা complex typography-এর visual approval নয়।

16-bit PNG flatten করার সময় 16-bit channel/alpha arithmetic থাকে। Odd still-image dimensions বজায় থাকে; video encoder-এর even-dimension policy আলাদা। JPEG default 4:4:4; `jpeg_chroma=420` explicit। PNG alpha default বজায় থাকে; JPEG-এর matte default black, `background` দিয়ে বদলানো যায়।

## HDR ও colour

Tone map-এর জন্য explicit `hdr_policy=tone_map`, known static PQ/HLG transfer, supported BT.2020/P3 signalling এবং caller-জানা `source_peak_nits` দরকার। Video output BT.709 limited; HDR image preset 16-bit full-range sRGB PNG দিতে পারে। পুরোনো mastering/CLL/ICC metadata SDR output-এ বহন হয় না। Dynamic HDR/Dolby Vision ও অজানা colour signalling অনুমান করা হয় না।

Analytic ramp-এর independent pixel calculation conversion পরীক্ষা করে। Publisher-এর `HDR_P3PQ` নামের বাস্তব excerpt-এ colour tags অনুপস্থিত পাওয়া গেছে; সেটিকে `hdr_metadata_required` দিয়ে refuse করা হয়েছে। Filename-কে metadata বা positive HDR proof ধরা হয়নি। Natural display judgement, reference mastering monitor ও perceptual grading এই স্থানীয় acceptance-এর অংশ নয়।

## Durable checkpoints ও scheduling

`checkpoint_seconds=5..600` কেবল zero-origin CFR video/audio ও source-এর একই explicit integer fps-এ supported। Runtime পুরো decoded frame timeline পরীক্ষা করে। সর্বোচ্চ ২,০৪৮ segment; VFR/nonzero-origin source সাধারণ transcode দিয়ে কাজ করে, checkpoint preset-এ refuse হয়।

প্রতিটি video segment full-decode/frame-count/hash যাচাই করে fsync ও no-clobber link-এর পরে manifest-এ লেখা হয়। Source content SHA-256, source identity, plan, workflow code ও binary/library binding মিলে তবেই retry-তে reuse হয়। Corrupted segment ও পুরোনো receipt রাখা হয়; নতুন unique segment বানিয়ে manifest এগোয়। Audio এক continuous AAC pass-এ encode হয়, যাতে প্রতি segment-এর AAC priming gap যুক্ত না হয়। Final mux আবার full validation পায়।

Higher-priority queued কাজ থাকলে validated segment boundary-তে job yield করতে পারে; FIFO/aging score-ও কার্যকর থাকে। Partial bitstream append করে resume হয় না। Spec/source/code/engine বদলালে নতুন plan অথবা একই frozen release-এ rollback প্রয়োজন।

## Failure containment ও publication

স্বাধীন guardian launch-এর আগে worker/supervisor identity, nonce ও kernel birth time নিবন্ধন করে। Worker, supervisor অথবা দুজন হারালে কেবল সেই কাজের owned process group থামে। Guardian host-lock FD ধরে রাখে; stop receipt-এর আগে lock reuse হয় না।

Attempt-এর total deadline, sampled 12 GiB footprint, disk/mount/output budget ও bounded logs বহাল থাকে। Long run-এর resource trace durable JSONL-এ থাকে; receipt-এর ছোট summary পুরো trace-এর বিকল্প নয়। এটি instantaneous kernel/GPU memory quota বা OS failure-এর universal guarantee নয়।

Final validated output link হওয়ার আগেই publish-intent লেখা হয়। Link হওয়ার পরে database update হারালে recovery plan/digest/inode/fingerprint/hash ও সফল full decode মিলিয়ে completed state reconcile করে। Invalid intent বা unrelated output গ্রহণ করে না।

## Immutable code/engine release

প্রতি release-এ allowlisted code files, engine snapshot, acceptance hashes ও manifest থাকে। `.runtime/active-release.json` একটি atomic pointer দিয়ে code ও native engine একসঙ্গে নির্বাচন করে। Queue/state আলাদা থাকে; previous selection ও release retained।

Install-এর আগে unit, native/extended media, performance, Phase 5, checkpoint, soak, formats, selected external FATE ও বাস্তব consumer—দশটি gate লাগে। Activation/rollback-এর exclusive lifecycle lock-এর বিপরীতে enqueue/retry shared lock নেয়। Queued বা চলমান কাজ থাকলে update থামে। নতুন release হওয়ার পরে পুরোনো MCP process-এর submit `release_changed` দেয়; read-only job status পাওয়া যায়।

Source checkout থেকে চালানো MCP-ও startup-এর workflow digest ধরে রাখে। পরে source edit হলে probe/plan/submit/retry/worker start `runtime_code_changed` দেয়; disk-এর নতুন hash দিয়ে memory-তে থাকা পুরোনো implementation-কে নতুন code হিসেবে চালায় না। Status/cancel/doctor inspection থাকে। Installed release-এর code files checkout edit থেকে আলাদা।

Queue fence নির্বাচিত ও default project state পরীক্ষা করে; shared host lock চলমান task-এ selection বদলাতে দেয় না। Arbitrary custom-state database discovery নেই। Custom queue-এর release command-এ একই `--state-dir` দিতে হয়; অন্য state-এর পুরোনো plan-এর code mismatch fail-closed থাকে।

`ffv2 exec --work-dir ... -- PROGRAM ARGS` trusted local consumer-কে private PATH-এ pinned `ffmpeg`/`ffprobe`/`ffplay` দেয়। Existing Studio worker-এর source না বদলিয়ে এই integration পরীক্ষা হয়। Parent process ও inherited process group watchdog-এর অধীনে থাকে; arbitrary detached service-এর sandbox দাবি নেই। এই raw trusted execution MCP-তে প্রকাশিত নয়।

RC থেকে final-এ শুধু version literals বদলালে সেই দুই file-এর before/after hash, অন্য সব functional file-এর equality ও fresh regression report bridge receipt-এ থাকে। RC-তে মাপা timing-কে final-এর নতুন measurement বলা হয় না। Functional change হলে নতুন gate evidence প্রয়োজন।

MCP client-এর configuration, fresh stdio round trip ও বর্তমানে খোলা chat-এর connection আলাদা। App-এর নিষিদ্ধ UI access এড়িয়ে hot reload-এর দাবি করা হয় না; নতুন connection verified installed launcher ব্যবহার করে।
