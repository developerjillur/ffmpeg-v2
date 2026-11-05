# Phase 10 — CPU contention ও x264 progress-query অনুসন্ধান

৪ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Active verified 0.6.0 এবং Phase 9-এর সব evidence retained। Candidate acceptance-এর আগে installed code/engine pair বদলানো হয়নি।

## পদ্ধতি ও স্থানীয় authority

একই retained BBB 1920×1080/30fps-এর 60–120s range এবং 60–90s-এর 900-frame raw reference। Encoder/decoder/filter pools 8/2/2, x264 veryfast/CRF20/lookahead2/sync4, software geometry/filter ও audio contract অপরিবর্তিত। New worker observer কেবল নিজের trusted diagnostic child-এ; production environment allowlist বদলায়নি। Instrumented timings speed promotion-এ ব্যবহার হবে না।

No-added-load ও নিজের দুই 50% wall-duty CPU worker দিয়ে replay। প্রতিটি load worker-এর প্রকৃত CPU consumption, parent identity, deadline, checksum ও window CPU ticks retained; kernel birth/process ownership ছাড়া অন্য process stop করা হয়নি। No-added-load মানে idle computer নয়। Actual host CPU ticks এবং residual activity রাখা হয়; background activity-কে নিয়ন্ত্রিত বলা হয়নি।

এই Mac-এ 10 performance + 4 efficiency cores; `xctrace` নেই। Public SDK `rusage_info_v6`, `CLOCK_THREAD_CPUTIME_ID`, pthread hooks ও host CPU counters ব্যবহার করা হয়েছে।

## CPU time, runnable time ও unit calibration

`rusage` user/system/P-core/runnable time Mach ticks-এ। Local timebase **125/3 ns per tick**। 0%, 50% ও 100% one-second duty calibration-এ converted kernel CPU time এবং thread CPU clock মিলেছে। 100% demand sample-এ CPU 0.846319s, runnable 1.000309s; অর্থাৎ CPU পাওয়ার অপেক্ষা প্রায় 0.153991s। Sleeping sample-এ wall 1.007350s হলেও CPU 0.000159s ও runnable 0.000431s। Runnable time running CPU-ও অন্তর্ভুক্ত করে; wait বের করতে CPU time বাদ দিতে হয়।

Per-worker CPU clock সরাসরি nanoseconds। Pthread wait wall time-এ signal/mutex reacquisition এবং wake-এর পরে scheduling delay একসঙ্গে থাকে; এটি pure blocked time নয়। Arbitrary wall-minus-CPU residual-কে runqueue wait বলা হয়নি। Process-level runnable counter থেকে aggregate ready-but-not-running delay পাওয়া যায়। Worker time যোগ করলে parallelism-এর জন্য process elapsed-এর চেয়ে বড় হতে পারে।

প্রথম observer প্রতি mutex-এ thread CPU clock পড়ছিল। HD retired instructions প্রায় 466B হয়ে baseline ≈386B-এর চেয়ে বেশি হয়; সেই observer throughput-এর authority নয়। V4 observer কেবল worker lifetime-এ CPU clock নেয়, uncontended mutex-এ timing syscall নেই এবং contended site আলাদা করে। V4 raw instructions ≈181.5–181.8B, frozen controls-এর একই স্তরে। প্রথম prototype ও failed setup receipts সংরক্ষিত।

V4 observer mutex acquisition-এ আগে trylock করে। এটি acquisition ordering ও timing বদলাতে পারে, তাই call count/callsite attribution-এর জন্য ব্যবহারযোগ্য হলেও তার timing uninstrumented performance-এর বিকল্প নয়। Process-only diagnostic build-এ pthread hooks বাদ দেওয়ার পথ আছে; CPU/runnable counters ছাড়া per-worker wait পাওয়া যাবে না।

V4 original/Stock উভয়ের shared Homebrew x264-এর জন্য তৈরি। Private dependency-তে profiling শুরুর আগে `otool`-এ observer-এর Homebrew link ধরা পড়ে; সেটি private candidate-এ ব্যবহার করলে দুই encoder load হওয়ার ঝুঁকি থাকত। V5-এ base/candidate/original-এর জন্য আলাদা observer exact matching dylib-তে link হয়েছে। Constructor actual encoder images এবং encoder-parameter function-এর image রেকর্ড করে; runner একটিমাত্র expected x264 image ও frozen output SHA বাধ্যতামূলক করেছে। Private V5 profiling এবং pthread-hook ছাড়া process-only profiling সম্পূর্ণ আলাদা reports।

V5-এর 16-site-per-worker bounded table-এ অল্প overflow হয়েছে। All-library overflow count-কে x264 count-এর সম্ভাব্য অতিরিক্ত অংশ ধরে conservative lower/upper bounds দেওয়া হয়েছে; হারানো site-কে শূন্য ধরা হয়নি। Recorded x264 lock calls প্রায় 98.4% কমেছে। এটি captured call traffic-এর পরিবর্তন, 98.4% encode-speed বা contention-time improvement নয়।

## Host saturation এবং engine mismatch-এর সীমা

Host counters-এ পরীক্ষার এক epoch-এ 14 core-ই ব্যস্ত। `top`-এ 70.61% user, 29.38% system, 0% idle এবং load average 43.4; `jpo perf`-ও saturation দেখিয়েছে। Observer-এর process CPU time ও runnable wait আলাদা হওয়ায় ওই epoch-এ pixel work বনাম CPU availability পৃথক করা সম্ভব হয়েছে। P-core share ও page-wait-ও মাপা হয়েছে; নির্দিষ্ট সব Native/Stock difference-কে E-core বা disk বলে ধরে নেওয়া হয়নি।

Native ও Stock একই original x264 ব্যবহার করলেও পৃথক run-এ ready queue wait আলাদা হয়েছে। তাই আগের slowdown-এর পুরোটিকে একটি encoder-algorithm defect বলা যাবে না। দুই engine-এই আরও একটি বাস্তব, পরিমাপযোগ্য কাজের খরচ পাওয়া গেছে: macroblock safety validation-এর progress query।

Raw-input cache residency-ও স্থির ছিল না। V5 worker profile-এ base raw run-এর disk read 2,801,655,808 bytes; পরের private run-এ 1,359,872 bytes। Process-only raw/no-added-load-এ original 2,800,918,528, candidate 7,753,728, Stock 737,280 bytes। সব source একই verified raw file; cold physical read ও cached read-কে encoder speed হিসেবে তুলনা করা হয়নি। CPU load replay এবং byte/frame identity থাকলেও file-cache state নিজে থেকে controlled হয় না। এই reports সম্ভাব্য contributors মাপে; আগের exact 9.53%/4.44%-এর পূর্ণ causal decomposition নয়।

## Hot mutex site ও pinned source

Homebrew formula থেকে exact x264 source revision **`b35605ace3ddf7c1a5d67a2eb553f034aef41d55` / r3222** নেওয়া হয়েছে; official VideoLAN Git থেকে শুধু প্রয়োজনীয় commit fetch হয়েছে। Installed Homebrew library অপরিবর্তিত।

V4 raw sample-এ একই internal site-এ **11,358,840** mutex calls; 21,234–25,606 contended acquisitions এবং aggregate wait প্রায় 0.83–0.91s পাওয়া গেছে। Library-এর nearest exported symbol প্রকৃত function-name নয়; call offset `0x17068`, disassembly-এর frame-progress load/negative-threshold branch এবং pinned source মিলিয়ে `x264_frame_cond_wait()` শনাক্ত করা হয়েছে।

`encoder/analyse.c`-এর motion-vector safety check প্রতি inter macroblock-এ `x264_frame_cond_wait(frame, -1)` দিয়ে progress পড়ে। Negative threshold-এ অপেক্ষা করার প্রয়োজন নেই, তবু original implementation mutex lock/unlock করে। Positive row waits এবং publisher broadcasts আলাদা প্রয়োজনীয় synchronization। `NDEBUG` দিয়ে safety check বন্ধ করা হয়নি।

## ছোট source fix

Private source commit **`6ffcc2c456e747189b9e1e4ac0f8d6b654f326c3`**:

- Apple arm64 threaded build-এ progress-এর সব writes release atomic store এবং reads acquire atomic load। Initialization, reuse reset ও publisher—তিনটি write site-ই রূপান্তর করা হয়েছে; mixed atomic/plain concurrent access রাখা হয়নি।
- Negative threshold-এর read-only query acquire load দিয়ে ফিরে আসে। Positive wait-এর original mutex/condition protocol এবং broadcast retained; lost-wakeup protocol বদলায়নি।
- Motion-vector check, warning ও recovery logic retained। Row pixels প্রকাশের আগে completed-line store এবং reader-এর data access-এর আগে acquire semantics বজায় থাকে। অন্য platforms পুরোনো path নেয়।

পরের source commit **`f70c7f8329264c9670d9fdcc1869376c7e001421`** deterministic progressive row wait-এ প্রত্যেক reference-এর acquired progress-এর minimum সংরক্ষণ করে। Safety check-এর exact required line এই published lower bound-এর মধ্যে হলে live value আবার পড়ার প্রয়োজন হয় না। Frame reuse-এ bound reset হয়; interlaced/non-deterministic mode-এ এই cache update হয় না; প্রয়োজন হলে original live check ও recovery চলে। Positive row-wait-এর পরে active reference-এর progress আর পেছায় না—এই invariant-এর ওপর cache নির্ভর করে। Diagnostic commit `eda8def54a8dc88d3d66bb79b541c6027939cf85` প্রতিবার cache ব্যবহার করার সময় live value-এর সঙ্গে অতিরিক্ত assertion চালায়।

এই invariant-এর সঠিক সীমা positive row-wait **ফিরে আসার পরে**। Source review-এ প্রথম filter publication initial −1 থেকে negative padding-এ নামতে পারে (`mb_y*16 − X264_THREAD_HEIGHT`); পুরো frame lifetime-এ অন্ধ monotonicity ধরে নেওয়া ঠিক নয়। Cached minimum positive wait-এর ফল থেকে আসে; initialization/reuse-এর −1 কোনো published row নয়। API stress-এ negative pre-publication-ও যোগ করা হয়েছে। Live assertion ও non-target regression এই boundary-ও পরীক্ষা করে।

Matched generic unpatched ও atomic-only builds একই compiler/options পেয়েছে। `-mcpu=apple-m4`+LTO variant HD encode-এ SIGSEGV পেয়েছে; receipt ও partial retained, variant rejected। LTO ছাড়া M4 build target HD/raw smoke পাস করেছে। Frozen confirmation candidate `rowvec`-এ row-progress patch, M4 target, `-fvectorize -fslp-vectorize` আছে; **LTO নেই**। Compiler tuning-এর লাভকে শুধু source patch-এর লাভ বলা হবে না। Original FFmpeg executable code ও Homebrew installation বদলায়নি; আলাদা staged prefixes-এ absolute dependency names ও ad-hoc signatures পুনর্গঠন করা হয়েছে। প্রতিটি closure-তে কেবল নির্দিষ্ট private x264 আছে। নতুন prefix stage করা activation নয়।

## Safety ও quality proof

Actual patched `frame.c`-এর 8-bit এবং 10-bit functions ThreadSanitizer দিয়ে compile হয়েছে। আট reader-এর অর্ধেক positive blocking wait এবং অর্ধেক negative progress query করেছে; immutable row payload publication এবং 16 reuse cycles পরীক্ষা হয়েছে। প্রতি depth **524,288 checks, 0 errors**, মোট **1,048,576**। এটি progress API-র proof; সম্পূর্ণ encoder-এর সব race-এর certification নয়।

Final row-progress source দিয়েও একই TSAN matrix পাস: `progress-tsan-20261104T064722-85c4b654/report.json`। Shadow assertion build-এর target encodes no-added-load ও দুই owned load worker—দুই অবস্থাতেই পাস করেছে; 1080p 1,800 এবং raw 900 frames। সব 16 smoke/control outputs retained। Assertion build throughput promotion-এ ব্যবহার হবে না।

Generic private base ও patched output-এর encoded SHA HD/raw দুটিতেই এক। Original Homebrew version-এর metadata আলাদা হওয়ায় তার quality অন্ধভাবে reuse হয়নি। নতুন all-frame metrics-এ candidate/original ΔVMAF=0, ΔPSNR-Y=0, ΔSSIM=0; HD 1,800, raw 900 frames। Size 14 bytes কম, যা encoded version metadata-র পার্থক্যের সঙ্গে সামঞ্জস্যপূর্ণ; শুধু size দেখে pixel identity দাবি করা হয়নি।

Final `rowvec` smoke-র দুই target SHA-ও একই quality-verified private output-এর সঙ্গে exact match; source/range/fps/encoding specifications, metric SHA ও all-frame coverage যাচাই করে quality reused হয়েছে। Confirmation-এর প্রতিটি output আবার hash করা হবে। Warmups ও profiling বাদ দিয়ে পৃথক no-added-load/added-load অবস্থায় **7 whole balanced blocks** predeclared। তিন engine-এর palindrome order block অনুযায়ী rotate হবে। Threshold বা slow trials পরে বদলানো হবে না।

## প্রাথমিক সূত্র

- [Apple XNU `fill_task_rusage`](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/bsd_kern.c): process CPU/P-core/runnable counters কোথা থেকে আসে।
- [Apple XNU task accounting](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/task.c): Mach-time fields, runnable timers ও performance-core usage।
- [Apple rusage_info_current](https://developer.apple.com/documentation/kernel/rusage_info_current): public SDK counter structure। Local SDK header ও live calibration ব্যবহৃত।
- [VideoLAN x264](https://code.videolan.org/videolan/x264): pinned local source-এর `common/frame.c`, `common/frame.h`, `encoder/analyse.c`, `encoder/encoder.c` ও `configure` authority। Browser access ব্যর্থ হলেও exact Git fetch সফল।
- Local Homebrew formula `/opt/homebrew/Cellar/x264/r3222/.brew/x264.rb`; actual source/build/closure receipts `<LAB_ROOT>/ffmpeg-v2-phase10`-এ।

চূড়ান্ত speed acceptance আলাদা independent uninstrumented confirmation, quality, full workflow ও regression gates-এর ওপর নির্ভর করবে।
