# Private x264 progress optimization

Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬। এটি Phase 10-এর experimental dependency; stage করা মানে active installed release নয়। চূড়ান্ত verdict `docs/PHASE10-RESULTS.md` এবং evidence index-এ থাকবে।

Official source `https://code.videolan.org/videolan/x264.git`-এর exact base `b35605ace3ddf7c1a5d67a2eb553f034aef41d55`। `manifest.json` patch order, hashes ও patched revision নির্ধারণ করে। প্রথম patch negative-threshold progress query-তে acquire load ব্যবহার করে; progress-এর সব writes release store হয়। দ্বিতীয় patch deterministic progressive row-wait থেকে acquired lower bound cache করে। Motion-vector check-এর required-line comparison এবং fallback warning/recovery বজায় থাকে। Positive wait/broadcast-এর original mutex/condition protocol থাকে। অন্য architecture পুরোনো path নেয়।

নিজস্ব source tree-তে base revision নিয়ে ক্রমানুসারে দুই patch `git am` দিয়ে apply করা যায়। কোনো existing source checkout, Homebrew dependency বা active engine overwrite করার প্রয়োজন নেই। Pinned source ও patches GPL-2.0-or-later; সম্পূর্ণ license `COPYING`-এ।

এই Mac-এর retained build receipts:

- `<LAB_ROOT>/ffmpeg-v2-phase10/x264-build-proof-base/build.json`: unpatched generic control।
- `<LAB_ROOT>/ffmpeg-v2-phase10/x264-build-proof-opt/build.json`: একই generic flags-এ প্রথম source patch।
- `<LAB_ROOT>/ffmpeg-v2-phase10/x264-build-proof-rowvec/build.json`: final source, `-mcpu=apple-m4`, vectorization enabled, **LTO ছাড়া**।
- `<LAB_ROOT>/ffmpeg-v2-phase10/x264-build-proof-check/build.json`: diagnostic live-progress assertion; production candidate নয়।

Out-of-source configure arguments: `--prefix=<new-private-prefix> --disable-lsmash --disable-swscale --disable-ffms --enable-shared --enable-static --enable-strip --disable-cli`। Candidate-এ C ও assembler flags-এ `-mcpu=apple-m4`; generated `config.mak`-এর `-fno-tree-vectorize` শুধু সেই নতুন build directory-তে `-fvectorize -fslp-vectorize` দিয়ে প্রতিস্থাপিত। `make -j2 lib-shared lib-static` এবং `make install-lib-shared install-lib-static`; exact argv/compiler/config receipts সংরক্ষিত। `NDEBUG` define করা হয়নি। M4+LTO variant encode-এ crash করায় rejected; সেটির ফল final candidate-এর proof নয়।

Upstream `version.sh` shallow source ও linked worktree-তে revision string তৈরি করে না। ফলে private control/candidate-এর SEI original Homebrew binary-এর চেয়ে 14 bytes ছোট। খালি revision-কে upstream r3222 হিসেবে উপস্থাপন করা হয়নি; source, patch, binary ও transitive library hashes authority। Pixel quality আলাদা all-frame metric এবং decoded-frame tests দিয়ে যাচাই করতে হবে।

`scripts/stage_phase10_engines.py` immutable original native install থেকে নতুন private prefix তৈরি করে এবং absolute dylib references পুনর্গঠন করে। Global Homebrew library এবং active code/engine pointer এতে পরিবর্তন হয় না। Runtime closure-তে অন্য x264 পাওয়া গেলে staging fail করে। Profiling hooks কেবল trusted diagnostic child-এ; production environment policy অপরিবর্তিত।
