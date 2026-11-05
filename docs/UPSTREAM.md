# Source fork, build ও update

Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬। বর্তমান [Phase 8 register](../PHASE8.md), [report](PHASE8-RESULTS.md) ও আগের [Phase 4–7 register](../PHASE4-7.md)-এ workflow/release acceptance আছে। নিচের source/build procedure system/Homebrew FFmpeg replace করে না।

Phase 8 wrapper 0.6.0-তে software concurrency/API/default উন্নত হয়েছে; native C source/binary/dependencies 0.5.0 থেকে একই। নতুন build বা FATE run প্রয়োজন হয়েছে এমন দাবি নেই। HD/ToS performance confirmation-এর জন্য `scripts/benchmark_phase8.py` / `scripts/analyze_phase8.py`, actual default proof-এর জন্য `scripts/verify_phase8_default.py` এবং final index/audit-এর জন্য `scripts/finalize_phase8.py`। পুরোনো `verify_phase4_default.py` 0.5.0-এর চার-thread defaults-এর historical verifier।

## Provenance

- Official repository: https://github.com/FFmpeg/FFmpeg.git
- Base tag n9.0.2; tag object ce8f11b9fac4cd7ccfb41ca7c01bc17f5cda8cc3।
- Peeled base commit 946fcce07b6dcd0331c8cc609192aeff5e1924f8।
- Local head b6e0de6e580ae325d5b12df79dddd364ccf11efb; branch ffmpeg-v2-main। Exact patched tree ও প্রতিটি patch SHA-256 manifest-এ।
- Source <LAB_ROOT>/ffmpeg-v2-core/ffmpeg; project local ignored symlink upstream/ffmpeg।
- Lock [upstream.lock.json](../upstream.lock.json), patch [manifest](../patches/manifest.json) ও [series](../patches/series)।

C patch নতুন global -progress_format jsonl option দেয়। প্রতি progress block একটি JSON line, schema_version=1, পুরোনো values strings। Default kv অপরিবর্তিত। Unknown format error দেয়। এটি encoder algorithm speedup patch নয়; programmatic clients-এর native structured progress extension।

দ্বিতীয় patch optional Metal runtime compiler, তৃতীয় patch VideoToolbox YADIF-এর autoreleased command objects-এর ownership/cleanup ঠিক করে। Stock-এর real cleanup SIGSEGV reproduction ও native GPU acceptance [Phase 2](PHASE2-DESIGN.md)-এ বর্ণিত। Upstream source/notice অক্ষুণ্ণ; public issue/PR/push হয়নি।

## Reproduce

~~~sh
ffv2 upstream status
ffv2 upstream prepare --plan
# শুধু source অনুপস্থিত থাকলে:
ffv2 --ignore-system-memory upstream prepare
python3 -B scripts/apply_patches.py
python3 -B scripts/apply_patches.py --apply
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/bootstrap_zimg.py
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/bootstrap_libass.py
ffv2 upstream build --profile m4 --jobs 2 --plan
ffv2 --ignore-system-memory upstream build --profile m4 --jobs 2
~~~

Existing checkout/source overwrite হয় না। Patch script checksum, locked base, clean tree ও host lock পরীক্ষা করে। Already-patched tree পুনরায় patch করে না। Jillur Rahman author/committer identity বজায় থাকে।

native profile optional codec-library parity ছাড়া bootstrap build। baseline profile existing codec libraries নেয়। m4 profile একই baseline সঙ্গে --cpu=apple-m4 এবং --extra-version=ffmpeg-v2-m4; Apple M4 brand পরীক্ষা করে। Default 2, supported serial 1 build job। Default resource policy এবং explicit override README-তে আছে।

pkgconf 3.0.10 local prefix-এ bootstrap হয়েছে; official archive SHA-256 9371b2f6372da574d4c6dc96fe9b1463037bcf6afcb6671c1555afde7b17e2de। scripts/bootstrap_pkgconf.py checksum-verified source ও guarded serial build ব্যবহার করে। Global package install প্রয়োজন হয়নি।

zimg 3.0.6-এর pinned official bottle থেকে private static archive, headers, pkg-config file ও licence রাখা হয়। Existing SDL2, codec libraries ও local pkgconf পুনর্ব্যবহার হয়; global Homebrew install বদলায় না।

Subtitle-এর জন্য libass 0.17.5 official archive-এর pinned SHA-256/size যাচাই করে private static archive build হয়। Existing CoreText/FreeType/HarfBuzz/FriBidi পুনর্ব্যবহার হয়; global install নেই। প্রথম configure diagnostics ও completed build receipt retained। নতুন candidate `m4-336aff836991d1b04d8a`-এর native source head একই `b6e0de6…`; configure feature addition-কে নতুন encoder algorithm বলা হয় না।

Build order: configure → compile → isolated install → NV12/P010 Metal smoke (baseline/m4) → fate-list → local FATE → binary/version/hash inspection। macOS absolute dylib install names-এর জন্য local API tests-এর আগে isolated install লাগে। এটি system install নয়।

Compile সফল হওয়ার পরে failure হলে source/tool/flags মেলা checkpoint দিয়ে install/FATE/inspection resume করা যায়:

~~~sh
ffv2 --ignore-system-memory --state-dir '/absolute/original/state' upstream resume --job-id FAILED_JOB_ID
~~~

Old logs/receipts থাকে; নতুন phase logs আলাদা নামে। Same identity-এর completed candidate ও binary hash মিলে গেলে build already_built দিয়ে cache reuse করে। Changed/mismatched candidate নীরবে replace হয় না।

## বর্তমান candidate ও release acceptance

Source checkout-এর `bin/ffv2` দিয়ে candidate verification/activation করুন। Installed `ffv2` frozen release-এর engine বদলাতে দেয় না; final code/engine pair বদলাবে `release install` দিয়ে। Existing engine stale হলে verifier explicit candidate prefix ব্যবহার করে; default system binary দিয়ে candidate pass দেখানো হয় না।

~~~sh
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_candidate.py --prefix '/absolute/candidate/install'
bin/ffv2 engine activate --manifest '/absolute/candidate.json' --verification '/absolute/printed/native-media/report.json'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_phase5.py --prefix '/absolute/candidate/install'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_phase6.py --prefix '/absolute/candidate/install' --mode quick --source '/absolute/retained-real-cfr.mkv'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_formats.py --prefix '/absolute/candidate/install'
~~~

`verify_candidate.py` 14 base, 21 extended GPU/HDR/fault/soak/MCP checks এবং before/after native/library closure যাচাই করে। একই source/package/script/report hashes মিলে তবেই completed diagnostic stage resume হয়। দীর্ঘ real-media performance, Phase 5/6, broader formats, selected external FATE ও existing Studio consumer-এর gates আলাদা। `collect_release_acceptance.py --help` দশটি report ও supplementary receipt-এর exact flags দেখায়।

`verify_release_lifecycle.py` measured RC acceptance থেকে actual install, queued/running update refusal, stale MCP refusal, cancelled checkpoint, version-only final update, rollback/reuse/full decode এবং user-local launcher পরীক্ষা করে। Script শুধু declared RC→final version literals বদলায়; functional change ঢুকলে refuse করে। Final version-এর fresh regression এবং RC-তে মাপা timing আলাদা করে record হয়।

Official external FATE samples-এর bounded subset ও target coverage `verify_external_fate.py` record করে। স্থানীয় 2,893 record এবং selected 15 external target এক সংখ্যা নয়। Full enabled external suite-এর 5,554 target এই acceptance-এ সম্পূর্ণ চালানো হয়নি। Sample SHA observed acquisition hash; signed publisher digest দাবি নয়।

## সংরক্ষিত Phase 2 procedure

নিচের commands historical Phase 2 proof reproduce করার জন্য। Current Phase 4–7 release-এর gate হিসেবে শুধু পুরোনো short benchmark যথেষ্ট নয়।

~~~sh
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_native_media.py --prefix '/absolute/install/prefix'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_phase2.py --prefix '/absolute/install/prefix' --mode all --sparse-source '/absolute/600s-fixture.mp4' --main10-source '/absolute/4k-sdr-main10.mp4'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/verify_mcp_pipeline.py --prefix '/absolute/install/prefix'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/benchmark_phase2.py --mode workflow --trials 7 --reference '/absolute/6s-720p-reference.mkv' --baseline '/absolute/v0.2.0-worktree'
FFV2_IGNORE_SYSTEM_MEMORY=1 python3 -B scripts/benchmark_phase2.py --mode core --prefix '/absolute/install/prefix' --trials 5 --reference '/absolute/6s-720p-reference.mkv'
# Printed native/media/MCP/benchmark report paths দিয়ে:
python3 -B scripts/finalize_phase2.py --manifest '/absolute/candidate.json' --native '/absolute/native-media/report.json' --report '/absolute/phase2-all/report.json' --report '/absolute/mcp/report.json' --workflow '/absolute/workflow-benchmark/report.json' --core '/absolute/core-benchmark/report.json'
ffv2 engine activate --manifest '/absolute/candidate.json' --verification '/absolute/native-media/report.json'
ffv2 engine status
ffv2 engine deactivate
~~~

Activation completed local FATE, matching native-media report এবং Phase 2 candidate-এর extended acceptance index চায়। Native-media test-এর আগে/পরে এবং activation-এর সময় library closure মেলে। GPU, HDR, sparse, corpus, fault, soak ও MCP reports-এর SHA-256 ও candidate identity পরীক্ষা হয়। Binary এবং transitive non-system dylib hash/identity/load paths রেকর্ড হয়। Homebrew opt symlink retarget হলেও stale selection ধরা পড়ে। Deactivation exact selection সংরক্ষণ করে। Active selection project-private .runtime/active-engine.json; system/Homebrew ffmpeg replace হয়নি।

Fresh checkout-এ fixtures আগে `verify_native_media.py`, `verify_large_media.py` ও `benchmark_native.py` দিয়ে তৈরি করে printed source paths explicit flags-এ দিন। Workflow comparison-এর baseline একটি retained v0.2.0 detached worktree; নতুন Python environment লাগে না। সব বড় job sequential চালান।

## Future updates

নতুন upstream security/release notice official sources থেকে যাচাই করুন। Existing source/lock/candidate সংরক্ষণ করে নতুন branch ও lock review, patch replay, local FATE, real matrix ও matched benchmark চালান। Acceptance ছাড়া selected engine বদলাবেন না। Full external-sample FATE, reproducible binary equality এবং public redistribution পৃথক কাজ। [Notices](../THIRD_PARTY_NOTICES.md), [FFmpeg development](https://ffmpeg.org/developer.html), [FATE](https://ffmpeg.org/fate.html)।
