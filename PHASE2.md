# Phase 2 — performance ও compatibility

শুরু: ২ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Baseline local release v0.2.0 সংরক্ষিত।

সম্পন্ন: **৩ নভেম্বর ২০২৬**। Local release **v0.3.0 activate হয়েছে**। [সম্পূর্ণ ফল ও comparison](docs/PHASE2-RESULTS.md), [acceptance receipt](docs/verification/phase2-2026-11-03.json)।

## লক্ষ্য ও গ্রহণযোগ্যতা

- [x] Optional runtime Metal compilation; stock cleanup SIGSEGV-এর পৃথক ownership fix; NV12/P010-তে 60 matched GPU frame hashes ও native exit 0।
- [x] ffplay build/launcher ও bounded headless dummy playback।
- [x] Verified capability cache, identity-only check, reusable independent supervisor; full decode/integrity বহাল।
- [x] Same-engine workflow comparison 7 trials; same-workflow stock/native comparison 5 trials; quality/size/negative results reported।
- [x] Natural Akiyo/Bus, 4K Main10, VFR/interlaced/rotation/truncated/playlist matrix, actual worker-kill/cancel/timeout ও real-time GPU soak।
- [x] Explicit PQ/HLG SDR policy, numerical ramp correction, bwdif ও 3-trial sparse sampling proof।
- [x] Full report, updated known gaps, retained baseline/source/build/results ও v0.3.0 local checkpoint।

সব success দাবি workload/version/receipt অনুযায়ী হবে। CPU/GPU/energy অথবা RAM savings-এর measurement ছাড়া শতকরা দাবি থাকবে না। Kernel hard-kill guarantee, production migration ও broad HDR correctness আলাদা evidence চাইবে।

এই task-এ owner-এর আগের explicit RAM/pressure override বহাল। Heavy কাজ sequential; per-job footprint, disk/mount/source/output checks বজায় থাকে। Build/download/cache mounted NexaWork/project-এ; অন্য apps/jobs বন্ধ করা হয় না।
