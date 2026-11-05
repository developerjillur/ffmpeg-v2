# Release গ্রহণযোগ্যতার সীমা

Maintainer: **Jillur Rahman**। ৪ নভেম্বর ২০২৬। Current completion status [Phase 8 register](../PHASE8.md), [Phase 4–7 register](../PHASE4-7.md), [STATUS.md](../STATUS.md) ও [VALIDATION.md](VALIDATION.md)-এর actual evidence দিয়ে যাচাই করতে হবে।

## Phase 4–8-এর gate

| Phase | কী প্রমাণ দরকার | প্রমাণের ধরন |
|---|---|---|
| 4 | Real long HD/UHD/live-action-এ repeated speed gain, একই predeclared quality/size gate | Frozen v0.4 baseline, warmup বাদে paired trials, full-decode/hash publish, all-frame VMAF/PSNR/SSIM; rejected hardware tuning-ও retained |
| 5 | Typed concat/subtitle/mix/HDR/image-এর actual timing/colour/audio/error output | Packet SHA, frame PTS/count, visible Bengali/ASS cue, independent PCM/DFT/limiter ও 16-bit/alpha/HDR pixel calculations |
| 6 | Long run, checkpoint ও interruptions-এর পরে correct output/recovery | Real elapsed 30-minute soak, 540s source batch, corrupt-segment rebuild/reuse, priority yield, worker/supervisor/both-loss, cancel/timeout/write-denial ও publish recovery |
| 7 | Existing local consumer/MCP, install/update/rollback ও broader compatibility | Real Studio timeline/reused parts, configured fresh MCP queue→worker→output, immutable pair, update fences, stale-process refusal, rollback checkpoint retry, format matrix ও selected external FATE |
| 8 | HD/live-action-এর quality-preserving throughput ও scoped eight-thread API/default | Frozen 0.5.0, separate calibration/নয়-pair confirmation, full-frame quality/size, same-tuned Stock disclosure, owned samples/adjacent stage isolation, actual source/installed CLI/MCP ও retained stable rollback |

শুধু exit 0, listed hardware, green unit test, configured entry বা ছোট fixture দিয়ে এই চার gate পূরণ হয় না। Implementation contract ও actual report-এর scope মিলতে হয়। [Design](PHASE5-7-DESIGN.md) ও [operations](OPERATIONS.md)।

## Runtime policy

Default invocation-এ normal pressure, independent memory headroom ও swap-growth check থাকে। Owner-এর explicit task waiver-এ `--ignore-system-memory`, `FFV2_IGNORE_SYSTEM_MEMORY=1` অথবা MCP worker-এর `ignore_system_memory=true` ব্যবহৃত হয়েছে। Default server configuration-এ permanent waiver যোগ হয় না। Sampled 12 GiB job footprint, mounted storage, boot/output disk, total timeout ও output checks বহাল থাকে; heavy media/build কাজ sequential।

Actual 30-minute real-media soak-এ 54,000 decoded frame, 1,800.021s output ও 355 durable sampled records আছে। Recorded peak ওই job/process tree-এর; পুরো computer বা অন্য apps-এর মোট memory নয়। এটি overnight reliability, instantaneous GPU quota বা kernel enforcement প্রমাণ করে না।

## স্থানীয় গ্রহণযোগ্যতার বাইরে

এই release একটি Apple M4 Max/macOS setup-এর measured presets ও bounded local workflow প্রমাণ করে। সব camera/VFR timeline, arbitrary HDR metadata, reference-display grading, overnight run, all hardware/codec pair, full external FATE, cross-platform calibration, reproducible binary distribution অথবা public deployment স্বয়ংক্রিয়ভাবে accepted হয় না।

Static known PQ/HLG conversion analytic output দিয়ে যাচাই হয়। Metadata-বিহীন real publisher HDR excerpt refuse হয়েছে; filename দেখে positive HDR success ঘোষণা হয়নি। Studio result technical integration acceptance; creative approval বা user-facing UI deployment নয়। Selected external FATE 15 target এবং local 2,893 record পৃথক; enabled external 5,554 target-এর পুরো suite চালানো হয়নি।

Install/update/rollback previous code/engine selection সংরক্ষণ করে; matching native libraries ও mounted storage প্রয়োজন। Library content/load path/device identity বদলালে strict selection fail-closed হয় এবং explicit re-verification লাগে। Current chat hot reload ও fresh configured connection আলাদা করে report করতে হবে।

পরবর্তী bounded research/workload বাছাই করা যাবে [known gaps](GAPS.md) থেকে। Historical [Phase 2](PHASE2-RESULTS.md) ও [Phase 3](PHASE3-RESULTS.md) short-workload ফল নতুন long-media timing-এর সঙ্গে এক epoch হিসেবে মেশানো হয় না।
