# Phase 2-এর সিদ্ধান্ত ও যাচাই

তারিখ: ২–৩ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Acceptance-এর ফল [PHASE2.md](../PHASE2.md) ও retained JSON receipts অনুযায়ী পড়তে হবে।

## Native compatibility

পুরোনো M4 build-এ `yadif_videotoolbox` বাদ পড়েছিল: Metal framework থাকলেও Command Line Tools-এ offline `metal`/`metallib` executable ছিল না। নতুন optional `--enable-metal-runtime` flag একই upstream shader source embed করে `newLibraryWithSource:options:error:` দিয়ে compile করে। Flag ছাড়া upstream binary-library path বহাল। Offline compiler-এর জন্য বড় Xcode download করা হয়নি। Listing-এর পাশাপাশি actual NV12/P010 GPU frames-এর hash installed offline build-এর সঙ্গে মিলিয়ে দেখা হয়। Runtime compilation-এর startup cost workload timing-এ থাকতে পারে।

`ffplay` SDL2-সহ build ও আলাদা launcher পায়। Acceptance headless dummy audio playback; graphical window, display calibration বা সব audio device-এর acceptance নয়।

Actual stock GPU run-এ cleanup SIGSEGV পাওয়া গেছে। Apple SDK-এর `commandBuffer` autoreleased return এবং `objc_release`/autorelease-pool crash trace-এর ভিত্তিতে পৃথক native patch-এ per-dispatch autorelease pool ও balanced ownership যোগ হয়েছে। Frame comparison-এ `-flush_packets 1` দিয়ে stock-এর সম্পূর্ণ decoded-frame hashes রাখা হয়; stock cleanup crash-কে successful process বলা হয় না। নতুন native process-কে exit 0 এবং একই 60 frame hashes দিতে হয়। Build-এ full FATE-এর আগে NV12/P010 GPU smoke চলে, যাতে এ ধরনের runtime failure দেরিতে ধরা না পড়ে।

`zscale`-এর জন্য zimg 3.0.6 static archive আলাদা project-specific prefix-এ ব্যবহৃত। Homebrew-এর official bottle SHA-256 pinned; global installation বদলায় না। Candidate binary-এর checksum ও complete non-system runtime-library closure সংরক্ষিত। Static zimg source/bottle provenance ও licence bootstrap receipt-এ থাকে; source rebuild-এর bit-for-bit reproducibility আলাদা বিষয়।

## Pipeline

Verified selected engine-এর executable ও library identity যাচাই করে capability result disk cache করা হয়। Cache identity ও content digest না মিললে fresh probe হয়; `doctor --refresh` দিয়ে পুনরায় query করা যায়। Unselected external binary-এর capability ফল persistent cache হয় না। Worker saved plan যাচাইয়ের সময় version/help/list child processes পুনরায় চালায় না; saved binary fingerprint ও selected engine binding পরীক্ষা করে।

এক worker pass-এর encode/full-decode phase একই independent supervisor reuse করে। Worker এখনও পৃথক process; supervisor প্রতিটি phase-এ admission, owner PID, cancellation, process-group shutdown, sampled footprint, disk, timeout ও bounded logs পরীক্ষা করে। Worker হারালে idle supervisor pipe EOF-এ শেষ হয়; active media owner-loss check-এ থামে। Supervisor-কে SIGKILL করার kernel guarantee যোগ হয়নি।

Receipts-এ preparation, supervised encode, metadata validation, supervised full decode, integrity/publish ও total সময় থাকে। Full decode, source/engine recheck, SHA-256 এবং atomic no-clobber publish বাদ দেওয়া হয়নি।

## Typed media policy

`deinterlace=bwdif` explicit হলে `send_frame` mode-এ interlaced frames progressive হয়; output frame rate দ্বিগুণ হয় না। Temporal filtering contact-sheet selection-এর আগে চলে। Default refusal বহাল।

`hdr_policy=tone_map` ও caller-supplied `source_peak_nits` দিয়ে known PQ/HLG BT.2020 non-constant matrix, known range source থেকে 100-nit BT.709 SDR transcode করা যায়। Linear float conversion, gamut conversion, Hable tone map, SDR encoding ও stale static HDR side-data removal হয়। Signalled dynamic HDR/Dolby Vision, incomplete metadata ও other wide-gamut policies প্রত্যাখ্যাত। Source peak-এর সত্যতা caller-এর দায়িত্ব; natural HDR colour-volume/display judgement এই numerical acceptance-এর বাইরে। HDR frame/sheet preset এখনো গ্রহণযোগ্য নয়।

Numerical PQ ramp test-এ RGB float metadata-এর জন্য desaturation luma ভুল হিসাব হওয়ার সমস্যা ধরা পড়ে। Tone mapper-এর আগে explicit linear BT.709 luma context দিয়ে এটি সংশোধন হয়েছে। zimg-এর default display-referred BT.709 conversion inverse BT.1886 gamma ব্যবহার করে; analytic calculation-এ সেই gamma থাকে। Test fixture-তে frame-level `setparams` দিয়ে transfer/primaries দেওয়া হয় এবং lossless HEVC VUI independently probe করা হয়। শুধু encoder colour options-কে metadata প্রমাণ ধরা হয় না।

Explicit `fps` না থাকলে transcode VFR timestamps বজায় রাখে; `fps` দিলে CFR output হয়। VFR acceptance decoded frame count ও PTS দিয়ে হয়।

Explicit `decode=videotoolbox` typed path-এ hardware output surface এবং `hwdownload` বাধ্যতামূলক। Supported 8-bit/10-bit 4:2:0 surface ছাড়া request refuse হয়। Unsupported decoder software fallback করলে hardware-only filter path ব্যর্থ হয়; সেটিকে hardware success বলা হয় না। Successful receipt-এ encoder ও decoder verification পৃথক থাকে। Zero-copy GPU scaling সব preset-এ যোগ হয়নি। Input processing-এ `-xerror` ও `-err_detect explode` দিয়ে decode error উপেক্ষা করা হয় না।

Contact sheet-এ `sampling=auto|single_pass|seek` আছে। Dense range এক pass decode করে। Long sparse range, count≤8, progressive input ও bounded decoder-memory estimate হলে auto multi-input seek ব্যবহার করে। একই process-এ bounded decoder count ও filter threads রাখা হয়। প্রতিটি branch-এর labelled source PTS target অনুযায়ী সাজিয়ে যাচাই করা হয়; log arrival order-কে frame order ধরা হয় না। Single-pass ও seek output-এর decoded pixels তুলনা করা হয়।

## Measurement

দুটি পৃথক comparison করা হয়: frozen একই engine-এ v0.2.0 বনাম Phase 2 workflow; এবং একই Phase 2 workflow-তে installed বনাম নতুন native engine। একটি warmup বাদ, seeded interleaved order, repeated median/range, exact source checksum ও retained outputs রাখা হয়। 720p/6s synthetic timing পুরো media market বা সব M4 workload-এর speedup প্রমাণ করে না। Natural talking/motion clips আলাদা functional corpus। 90-second real-time encode wall-clock soak; 600-second media timeline-কে 600-second soak বলা হয় না।

## Primary references

- [Apple Metal runtime compilation API](https://developer.apple.com/documentation/metal/mtldevice/makelibrary(source:options:)) — API এবং installed SDK declaration মিলিয়ে implementation।
- [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html) — `bwdif`, `zscale`, `tonemap`, `select`, `xstack`; locked local source ও filter help authoritative implementation reference।
- [Official Homebrew zimg metadata](https://formulae.brew.sh/api/formula/zimg.json) এবং [recipe](https://github.com/Homebrew/homebrew-core/blob/HEAD/Formula/z/zimg.rb) — version, SHA-256, source ও licence।
- [zimg 3.0.6 transfer implementation](https://github.com/sekrit-twc/zimg/blob/release-3.0.6/src/zimg/colorspace/gamma.cpp) — display-referred BT.1886 ও ST2084 numerical reference।
- [Xiph test-media collection](https://media.xiph.org/video/derf/) — small talking/motion corpus; collection-এর copyright caveat সংরক্ষিত, raw media private QA-তে রাখা হয়।
