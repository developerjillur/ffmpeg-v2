# Phase 11 — CPU/cache conditioning এবং private PGO

Maintainer: **Jillur Rahman**। শুরু৪ নভেম্বর; bounded evaluation শেষ৫ নভেম্বর২০২৬ (Asia/Dhaka)। Base `a6cae26`; initial baseline release `0.6.0-fc5c8de8ba2a58f7`। এই নথিতে implementation, calibration ও acceptance আলাদা evidence। [Final ফল](PHASE11-RESULTS.md) এবং [cold verification index](verification/phase11-2026-11-05.json) তৈরি হয়েছে।

**Final admission method:** global CPU busy≤6 cores-এর eight consecutive credible samples; preferred span≤0.75 core। Exploratory classification-ও busy≤6 শর্ত মানে। Parent wait-এর সময় source unpinned; fresh disk reserve ছাড়া cache hold হয় না। এই নথির max14.5 ও earlier admission আলোচনা calibration/revision history। Evaluation শেষ: complete HD workflow Stock থেকে1.743%/1.791% কম elapsed with9 valid blocks/load, কিন্তু direct HD/raw-এর required samples অসম্পূর্ণ। Overall promotion gate fail; private candidate default নয়।

Latest scheduling: corrected run-এর3600s wait budget শেষ হয়েছে,12 warmup ও0 measured cases/attempted blocks retained। নতুন passive watcher first30 consecutive1s sample-এর busy≤6/span≤0.75 ও disk reserve চায়; no mappings/encodes while waiting। একবার ready হলে একটি independent confirmation launch করে; actual inner admission, whole-block gates, nine-block requirement ও confidence method একই। Any measured row/attempt, resource stop, changed policy বা live cache থাকলে trial reset নিষিদ্ধ।

Watcher নিজে window পেয়ে final direct run launch করেছে:688 completed cases/180 attempted blocks, valid1/1/3/7 বনাম required9 per group। Separate complete workflow144 cases/23 blocks-এ18 accepted blocks। Existing raw diagnostic ratios favourable হলেও3/7 blocks release proof নয়; previous+new CPU conditions একত্রে নিয়ে পুরোনো9.53% বা4.44% gap-এর universal closure দাবি করা হয়নি।

## সমস্যার নির্দিষ্ট কারণ ও সংশোধন

| পর্যবেক্ষণ | ফলের ওপর প্রভাব | Phase 11 পরিবর্তন |
|---|---|---|
| Short-lived child শেষ হওয়ার পরে parent scheduling delay | Parent elapsed-এর মধ্যে unrelated wakeup delay মিশে যায় | Child-এর kernel start/exit absolute time; zombie অবস্থায় final `rusage_info_v6`, তার পরে `wait4` |
| Short-window `host_statistics` counters বারবার cached value ফেরত দেয় | 14-core host-এ apparent capacity 0–56; background load estimate গ্রহণযোগ্য নয় | `host_processor_info(PROCESSOR_CPU_LOAD_INFO)`; returned VM ও host port release; capacity calibration এবং `top` cross-check |
| Raw source-এর file cache compressed/evicted হতে পারে | Encode speed-এর সঙ্গে physical I/O ও page-fault time মিশে যায় | একই 2,799,360,000-byte file read/touch; bounded temporary `mlock`, pre/post `mincore`; source identity অপরিবর্তিত |
| Executable/shared libraries-এর first-read imbalance | Input cached থাকলেও engine startup I/O আলাদা হয় | Exact non-system runtime closure সাময়িক pin; max128 images/256MiB; measured read budget8MiB |
| Read-only system-installed image-এর `MAP_SHARED` lock-এ `EPERM` | কয়েকটি prototype-এ conditioning অসম্পূর্ণ | Image mappings `MAP_PRIVATE`; input `MAP_SHARED`; protection/lock limits বা original library বদলানো নয় |
| Host সত্যিই প্রায় saturated; max10 admission-এ 12 PGO calibration case-ই launch-এর আগে rejected | Quiet-only detector meaningful stable saturation ব্যবহার করতে পারে না | Confirmation-এর আগে v6 max14.5; আট consecutive 1s sample-এর span≤0.75 core; during-run matching এবং relative delivered-CPU span≤10% যোগ |
| Source row-progress improvement-এর পরে generic C code layout | Algorithm না বদলে remaining CPU work কমানোর সুযোগ | একই clean source/tree থেকে Apple M4 vectorization এবং profile-guided optimization; LTO নেই |

Counter API পরিবর্তন নিজে codec throughput improvement নয়। Cache pinning cold-disk throughput বাড়ানোর দাবি নয়; এটি তুলনার warm-cache অবস্থাকে স্পষ্ট ও একই রাখে। Conditioning/warm-read cost child lifetime-এর বাইরে এবং আলাদাভাবে সংরক্ষিত। Host cache purge, CPU affinity, priority boost অথবা unrelated apps বন্ধ করা হয়নি।

## Primary technical evidence

Apple-এর [XNU `host.c`](https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/kern/host.c)-এ third-party host-statistics caching আছে। তাই timer cadence থাকলেই counter fresh—এমন অনুমান করা হয়নি। Live per-core delta ও 14-core capacity যাচাই করা হয়েছে। Local SDK-এর `mach/processor_info.h`, `sys/resource.h`, `sys/mman.h` এবং [XNU recount documentation](https://github.com/apple-oss-distributions/xnu/blob/main/doc/observability/recount.md) দিয়ে counter field/units পরীক্ষা হয়েছে।

Apple-এর [`time` implementation](https://raw.githubusercontent.com/apple-oss-distributions/shell_cmds/main/time/time.c)-ও child reap-এর আগে final resource information সংগ্রহ করে। এখানে নিজস্ব parent-side launcher ব্যবহার করা হয়েছে। Direct/descendant/short-child calibration-এ Mach timebase125/3 এবং inclusive `wait4` CPU মিলেছে; final counter ও wait accounting-এর পার্থক্যও admission gate।

[Clang PGO documentation](https://clang.llvm.org/docs/UsersManual.html#profile-guided-optimization) অনুযায়ী instrumented training, `llvm-profdata merge`, তারপর profile-use build করা হয়েছে। Multi-thread training-এর জন্য atomic profile update; use build-এ stale-profile diagnostic fatal। Final dylib-এ profile instrumentation symbols অনুপস্থিত। Sources ৪ নভেম্বর ২০২৬-এ পরীক্ষা করা হয়েছে; actual flags ও compiler version local receipts-এ authoritative।

## Reproducible candidate

- Source: upstream [VideoLAN x264](https://code.videolan.org/videolan/x264), base `b35605ace3ddf7c1a5d67a2eb553f034aef41d55`, patched `f70c7f8329264c9670d9fdcc1869376c7e001421`, tree `09f3cac3e1d192f70f8b2ca6d13aee552a1aa5b3`। Exported patches/license `third_party/x264/`-এ; original source worktree clean।
- Training: BBB20–25s/150frames; TOS30–35s/120frames; generated10-bit640×360/60frames। Confirmation BBB60–120s এবং raw60–90s; overlap নেই। Corpus generalization দাবি নয়।
- Compiler: Apple Clang21.0.0; `-mcpu=apple-m4 -fvectorize -fslp-vectorize`; generate-এ `-fprofile-instr-generate -fprofile-update=atomic`; use-এ `-fprofile-instr-use -Werror=profile-instr-out-of-date`। LTO ও `NDEBUG` নেই।
- Profile:1202 functions/15721blocks; total block count2,282,909,684। Exact raw profiles, merged profile, config hashes, outputs ও10 successful step receipts retained।
- Build recipe: `scripts/build_pgo_phase11.py`; proof `<LAB_ROOT>/ffmpeg-v2-phase11/pgo/report.json`; candidate `<LAB_ROOT>/ffmpeg-v2-phase11/pgo/candidate.json`। Private install-এর absolute runtime closure-এ কেবল তার নিজস্ব x264 bind হয়েছে। Homebrew ও active default bytes অপরিবর্তিত।
- Private source-এর upstream shallow/worktree version metadata ফাঁকা; original-এর তুলনায় container14bytes ছোট। Source/profile/binary SHA দিয়ে provenance, upstream version impersonation নয়।

## Quality এবং independent confirmation

PGO full outputs-এর encoded SHA Phase10 quality-verified private outputs-এর সঙ্গে exact match; source/spec/metrics/output SHA যাচাই করে all-frame metrics reuse। Fresh strict decode-এ HD1800video ও2813audio frame, raw900video frame-এর timestamps/size/SHA256 Stock ও active default-এর সঙ্গে exact match। VMAF/PSNR-Y/SSIM delta0। Files external quality directory-তে retained; timing কখনও quality gate-এর বিকল্প নয়।

Final direct confirmation-এ একই source, scale/FPS, CRF20/veryfast, encoder8/decoder2/filter2 এবং legacy progress contract। তিন engine-এর complete palindrome order ঘুরে যায়; প্রতি HD/raw × own-load0/2 group-এ9 accepted whole blocks প্রয়োজন। Max45 attempts/group এবং মোট automatic admission wait≤3600s; rejected block ও অসম্পূর্ণ attempt-ও retained। Warmups final timing থেকে excluded। কোনো slow-time filter নেই।

Readiness scheduling correction: প্রথম frozen run-এ0 accepted blocks, কোনো accepted-block speed analysis হয়নি। Strict idle-window detector প্রায়20 মিনিট নতুন attempt আটকে রেখেছিল। First run/22 rows/two rejected attempts ও frozen sources retained। পরে নতুন independent run-এর আগে preferred eight-sample preflight-এর পাশে15s পরে credible-counter exploratory block যোগ হয়। এটি observed block inclusion threshold শিথিল করে না: actual background/P-share/delivered-CPU/load/cache/I/O এবং nine-block/quality/confidence rules অপরিবর্তিত। Preflight-stable ও exploratory classification report-এ পৃথক; previous unaccepted timing নতুন confirmation-এ মেশে না।

Frozen v6 validity: background span≤0.75core; direct within-run background IQR≤1core; P-instruction share span≤0.03; delivered CPU relative span≤10%; own synthetic load span≤0.15core, actual duty0.50–1.05core; source residency≥99.99%; image mappings locked/resident; direct physical reads≤8MiB; capture delay≤50ms; CPU capacity14±0.5; final inclusive CPU accounting tolerance=max5ms/0.1%। Matched CPU ও P-share environment gates speed-এর বিকল্প নয়। Thermal/frequency state pin করা হয়নি; ফল এই workload ও admitted conditions পর্যন্ত সীমিত।

Estimator: প্রতি block-এর candidate mean/reference mean-এর geometric mean;20,000 whole-block bootstrap draws, seed2026110411। Stock এবং active Native—দুই reference-এর বিরুদ্ধে সব required group-এ95% upper ratio<1 হলে direct speed gate pass। Insufficient valid blocks-কে successful proof বলা হয় না; calibration/failed run যোগ করে sample count পূরণ করা হয় না।

Complete typed HD workflow-তে একই SDK এবং8/2/2/8 pools; full process lifetime-এর মধ্যে planning/encode/strict decode/hash/no-clobber publish। Final inclusive child CPU দিয়ে whole-block background ও delivered CPU match করা হয়। Root-only disk/P-share/live CPU-কে descendants-এর counter বলা হয়নি; direct-encoder gates ও pipeline gates আলাদা। Public/default promotion-এর জন্য complete workflow-ও pass করতে হবে।

## Resource scope ও acceptance boundary

সব heavy work sequential; compiler≤2 jobs; own nice≥10। Source mapping≤3GiB, image set≤256MiB, task estimate≤8GiB; own hard footprint12GiB। Existing task-specific memory waiver কেবল authorized invocation-এ; default production policy বদলানো হয়নি। Disk/mount/deadline/output guards বহাল। সব বড় data/builds `<WORK_VOLUME>` অথবা project volume-এ। Internal boot hard limit400GB; unrelated app/process lifecycle অপরিবর্তিত।

Cache lease correction ও actual resource interruption: initial per-case mapping প্রায়2.85GB wire/unwire করে; run-এর মাঝখানে cache100% হলেও comparator-গুলোর মাঝে RAM স্থির ছিল না। Whole-comparison source union3,075,494,947bytes এবং image union93,497,728bytes-এর real calibration pass। তবে subsequent full calibration-এ boot_used400,071,602,176bytes হওয়ায় child guard raw case থামায়; six completed HD warmups ও all artifacts retained। এটিকে timing acceptance বলা হয়নি।

Lower-demand final conditioning-এ parent কেবল paired block চলাকালে one input ও common image union lock করে; wait চলাকালে lock নেই। সব six comparator একই lease_id বহন করে; before/after source/image identity ও residency prove হয়। Source≤3GiB/image≤256MiB, conservative total estimate8GiB। Shared file-backed mappings `physical_footprint`-এ পুরোপুরি charged নয়—real3.08GB source lock-এ owner footprint মাত্র116MB observed। তাই task-local0.5s watchdog process-tree footprint-এর সঙ্গে held mapped bytes conservatively যোগ করে12GiB stop enforce করে; child supervisorও বহাল। Fresh admission-এ cache bytes+2GiB boot margin চাই,400GB hard stop অপরিবর্তিত। Resource wait-এর সময় zero pinned source এবং automatic CPU/disk detector active। Failed/partial allocation-এর cleanup, read-only unchanged source ও omitted file-cache reservation-এর negative checksসহ দুই runtime163 tests pass।

Reliable performance proof ছাড়া candidate default হবে না। Proof pass হলে actual new-prefix native/FATE/media/GPU/fault/soak এবং install/update/rollback/CLI/MCP lifecycle নতুন করে দরকার; copied old receipts promotion acceptance নয়। Proof fail হলে0.6.0 retain করে exact failure ও remaining gap report করা হবে।

SDK ABI cross-check-এ parent Python checker-এর bit error পাওয়া যায়: `MINCORE_REFERENCED_OTHER=0x08`, `MINCORE_PAGED_OUT=0x20`; C launcher actual SDK macro ব্যবহার করায় তার timed-child residency checks correct ছিল। Parent mask corrected; both bit patterns independently tested। Corrected raw-cache real calibration pass ও165 tests/runtime pass। Prior full paired-cache run mandatory raw30/load2 group-এর45 environment attempts-এ0 accepted blocks; positive performance proof অসম্ভব, সেই incomplete run/other partial cells retained। পরের run-এ global preflight≤6cores—stable saturation14 actual CPU/P-share match দেয়নি। এটি admission tightening; actual case/block/quality/confidence thresholds বা candidate/settings শিথিল করা হয়নি। Prior timings নতুন run-এ imported নয়।

## Mount identity recovery ও fresh baseline

পরবর্তী regression-এ `engine_changed` ওঠে: external work volume-এর runtime device16777246→16777247। All38 selected native files cold SHA256/alias/inode/size/mtime exact; byte change নেই। JPO volume UUID check pass; NexaWork UUID `<VOLUME_UUID>`। Strict guard retained। Original engine fresh native14 দিয়ে explicitly reactivated; exact original frozen45-file0.6 package metadata-only নতুন pair-এ installed। Old manifest/releases/proofs untouched। Existing finalized RC→final version-transition acceptance retained; generic collector পুরোনো RC timing-কে current final SDK হিসেবে পুনরায় মানেনি, সেই rejection log-ও retained। New same-SDK176-test two-runtime regression এবং fresh native/source+installed CLI/MCP verification আলাদা evidence। এটি নতুন PGO performance acceptance নয়।

Current release `0.6.0-e07af57a8214502f`; original native content unchanged। Ledger `<LAB_ROOT>/ffmpeg-v2-phase11/mount-recovery-20261104T153507/report.json`; original `initial.json` retained এবং new `baseline.json` তার SHA-তে bound। Timing/workflow/finalizer-এ `--baseline` শুধু explicit revalidated epoch নেয়; child argv, counters, cache, validity ও statistics বদলায় না। New timing-এ baseline hash freeze/end-check এবং release audit-এ reference-library binding আছে।

PGO binary/profile/source bytes unchanged রেখে filesystem metadata refreshed manifest; fresh6 complete encodes আগের golden SHAs-এ match, metrics delta0, all-frame decoded identity আবার pass। Fresh original/PGO native14 ও source/installed CLI/MCP controls pass। Unsuccessful old run থেকে কোনো timing import করা হয় না। Current paths এবং watcher PID/birth external `CONTINUATION.json`-এ authoritative।

Final fallback recovery-তে retained original0.5 package-এর stale device metadata-ও full original package/native SHA proof ধরে revalidated। Actual rollback→installed0.5 CLI/MCP→return0.6 CLI/MCP pass; healthy fallback `0.5.0-018d61f631128c48`। PGO কখনো active হয়নি। Primary final index-এ recovery ও rollback supplements-এর SHA আছে; first-pass derived report external task archive-এ retained।
