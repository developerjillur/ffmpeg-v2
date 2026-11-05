# FFmpeg-v2 লক্ষ্য

Maintainer: **Jillur Rahman**। আপডেট ৪ নভেম্বর ২০২৬।

Mac-এ বড় media কাজের জন্য উন্নত FFmpeg fork, optimized workflows, CLI ও agent/MCP interface তৈরি এবং প্রমাণিত bottleneck অনুযায়ী উন্নয়ন করা এই project-এর লক্ষ্য। প্রথম local release 0.2.0, [Phase 2 release 0.3.0](PHASE2.md), [Phase 3 release 0.4.0](PHASE3.md) এবং [Phase 4–7 release 0.5.0](PHASE4-7.md) সম্পন্ন। বর্তমান Phase 8 local release **0.6.0**: HD/live-action-এর পুরোনো concurrency cap, quality-preserving tuning, independent nine-pair performance ও actual release/agent checks। [নতুন report](docs/PHASE8-RESULTS.md), [register](PHASE8.md) ও [evidence](docs/verification/phase8-2026-11-04.json)।

Phase 8-এ একই safeguards-সহ আগের Stock preset থেকে HD/ToS সময় 22.61%/28.48% কমেছে; পুরোনো Native থেকে 22.31%/30.77%। Matching quality/size gates pass। একই নতুন tuning-এ Native/Stock-এর intervals equality পার করে; raw-feed control-এ 4.44% gap retained। Stable 0.5.0 rollback-এর জন্য আছে। Other hardware/codec/private-camera, overnight ও public reproducible distribution এখনও নিজস্ব bounded verification চায়।

## Phase 1-এর সংরক্ষিত checkpoint

- [x] স্বতন্ত্র local repository ও exact upstream source/tag/commit lock।
- [x] Local source fork, reviewable C patch, patch checksum ও replay procedure।
- [x] Apple M4-specific compiled binary; successful local FATE run।
- [x] পাঁচটি typed operation, durable queue/idempotency, cancellation/retry, supervisor ও validated publish।
- [x] Real nonzero audio, H.264 software/VideoToolbox, exact-source-PTS frame, contact sheet ও remux।
- [x] Dense sampling-এ এক pass-এর implementation; তিন trial-এ 14.11× measured pipeline ratio, একই frame timestamps।
- [x] Installed/native repeated encode comparison; aligned VMAF/SSIM ও limitations।
- [x] 4K HEVC Main10 hardware encode/decode, 1080p conversion ও bit-depth-preserving remux।
- [x] 600s timeline, 18,000 video frame, full decode, A/V endpoints 600.0s।
- [x] CLI ও real MCP submit→worker→output; sole local engine selection এবং user-local launchers।
- [x] Binary/non-system library hashes, load-path integrity ও reversible engine deactivation।
- [x] ৭০টি regression/control test, দুই Python runtime; local source checkpoint ও handoff।

## Scope ও পরের উন্নয়ন

Phase 2-তে native Metal availability/cleanup crash, repeated query/startup cost, sparse seek, explicit PQ/HLG/interlace/hardware-decode policy, VFR/rotation/corruption, natural clips, actual process-loss recovery ও real-time GPU soak-এর acceptance হয়েছে। 80 control tests, 2,893 local FATE records ও candidate-bound report index আছে। Same-engine transcode/dense job time 35.87%/46.38% কম; Phase 2 single-pass→sparse seek 16.57×। [সম্পূর্ণ ফল](docs/PHASE2-RESULTS.md)।

Phase 3-তে custom-binary dependency cache, native resource API, ctime-bound plans, priority/aging ও supervisor-loss backup হয়েছে। Same-engine native software pipeline ১৫ trials-এ 21.44% এবং actual CLI process ৯ trials-এ 17.75% কম সময় নেয়; byte-identical output। Hardware-frame scaling opt-in; tested short fixture-এ ধীর/quality কম হওয়ায় default হয়নি। [ফল](docs/PHASE3-RESULTS.md)।

Phase 4–7-এ দীর্ঘ বাস্তব HD/UHD/live-action-এর চার software profile-এ v0.4 workflow থেকে সময় 17.75%, 16.91%, 14.53% ও 24.31% কমেছে; সব predeclared speed/quality/size gates pass। Typed concat/subtitle/mix/HDR/image, durable checkpoint/preemption/recovery, 30-minute elapsed soak, 540s real batch, installed Studio integration, actual install/update/rollback, configured installed MCP, broader formats ও selected external FATE সম্পন্ন। Stock/native-এর চার interval-ই সমান সময় অতিক্রম করে; universal native superiority দাবি নেই। Overnight/private-camera/perceptual HDR, full external FATE ও cross-platform/distribution research tested scope-এর বাইরে। [GAPS.md](docs/GAPS.md)।

সর্বশেষ owner নির্দেশে এই task-এর run-এ RAM/pressure stop উপেক্ষা করা হয়েছে। পূর্বের resource-blocked stage ঐতিহাসিক। Runtime default policy, explicit override ও receipt-এর পার্থক্য [README.md](README.md)-এ আছে।
