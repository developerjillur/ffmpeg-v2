# Phase 3 implementation — 0.4.0

৩ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Native C core ও active binary অপরিবর্তিত; এই release workflow, runtime identity, queue ও recovery উন্নত করে।

## Software overhead

পুরোনো stock/native report-এর native capability lookup median 0.279127s, stock 0.160582s ছিল। Actual work median প্রায় সমান ছিল। শুধু encoder দ্রুত করলেই এই discovery overhead সরত না।

Capability cache এখন selected engine এবং explicit custom Mach-O binaries দুটির জন্য। Cold inspection binary/non-system dylib closure, SHA-256 ও resolved load paths নেয়; content আবার মিলিয়ে SHA-256 ও নতুন `ctime_ns`-সহ identity একই read window-তে bind হয়। Cache hit-এ OS/kernel/machine/DYLD environment, file identity ও alias resolution পরীক্ষা হয়। Source plan-এও `ctime_ns` আছে। Same-size modification-এর পরে `mtime` ফিরিয়ে দিলেও নতুন plan/library checks reject করে।

Cached payload-এর digest accidental corruption শনাক্ত করে। Saved plan সম্পূর্ণ runtime binding বহন করে; cache file সরালে valid plan নষ্ট হয় না। Before encode, validation ও publication binding আবার দেখা হয়। Optional cache directory blocked হলে valid query বন্ধ হয় না। Unresolved `@rpath` বা injected DYLD closure নির্ভরযোগ্যভাবে inspect করা না গেলে fresh query হয়; সেই result persist করা হয় না। একই macOS user-এর arbitrary hostile code-এর বিরুদ্ধে filesystem sandbox দাবি নেই।

## Resource API ও validation

Default `auto` backend macOS `host_statistics64`, `sysctlbyname`, `proc_listchildpids` ও `proc_pid_rusage` ব্যবহার করে। SDK-verified VM statistics prefix, page size, active/wired/compressor, swap এবং physical footprint আগের policy-র একই হিসাব দেয়। প্রতি sample-এ helper `ps`, `sysctl` বা `vm_stat` process লাগে না। Mach host port release হয়; child traversal bounded। Exited children-এর race আলাদাভাবে সামলানো হয়।

Native API unavailable হলে `auto` পুরোনো CLI backend-এ যায়। `FFV2_RESOURCE_BACKEND=native|cli|auto` diagnostic selection দেয়। Forced native footprint unavailable হলে job guard fail closed; metadata helper-ও unavailable measurement নিয়ে কাজ চালায় না। Scoped owner RAM waiver, 12 GiB job limit ও disk/mount/timeout checks আগের মতো থাকে।

পূর্ণ output decode এখনো `ffmpeg -xerror -err_detect explode ... -f null` দিয়ে হয়। `ffprobe -count_frames` দিয়ে এটি প্রতিস্থাপিত হয়নি: pinned source-এর frame-reading loop decoder-এর negative return সরাসরি process failure বানায় না। শুধু count/exit code দিয়ে strict decode acceptance দুর্বল হতো। Empty pipe selector-এর অপ্রয়োজনীয় 150ms wait সরানো হয়েছে; pipes বন্ধ হলেও watchdog timeout/cancel check থাকে।

## Queue priority ও aging

সব typed media spec-এ optional integer `priority=-10..10`; default 0। Existing database-এ additive column migration হয়; jobs/receipts মুছে যায় না। Claim-এর order `priority + age_seconds/60`; shared current time বাদ দিলে `priority*60-created` একই ordering দেয়। Equal-priority jobs FIFO। 20 মিনিটের বেশি পুরোনো priority −10 job নতুন priority +10 job-এর আগে আসে; execution-start deadline বা preemption-এর নিশ্চয়তা নয়।

Explicit `--job-id`, cancellation, idempotency, output reservation ও resource-deferred exclusion বহাল। Retry পুরোনো creation time রাখে। Running job interrupt করে নতুন urgent job চালানো হয় না। MCP একই schema ব্যবহার করে; real client-এর urgent job আগে complete হওয়ার receipt যাচাই করা হয়েছে।

## Supervisor loss

Supervisor media spawn করার পরে private nonce, worker/supervisor PID, media PID ও kernel birth timestamp নিবন্ধন করে। Receipt pipe হারালে জীবিত worker supervisor reap করে এবং শুধু matching registration, birth identity ও process group-কে TERM/KILL করতে পারে। Changed/reused PID বা nonce mismatch-এ signal দেওয়া হয় না। Diagnostic one-phase calls-ও এই session/recovery path ব্যবহার করে।

Actual supervisor SIGKILL test-এ media stopped, output absent এবং host lock released। Existing worker SIGKILL/cancel/timeout tests-ও আবার pass। Registration লেখার আগের window, simultaneous worker+supervisor SIGKILL ও kernel-enforced parent-death guarantee এখনো সীমা। Background daemon/launch agent install করা হয়নি।

## Hardware-frame scaling

Optional `filter_backend=videotoolbox` typed transcode-এ `scale_vt` ব্যবহার করে, explicit CPU `hwdownload,format,scale` chain সরায়। VideoToolbox decode ও encode, 8-bit 4:2:0 SDR, square pixels, progressive/unrotated geometry প্রয়োজন। Unsupported combinations typed refusal পায়। Default `filter_backend=software`। Driver-এর অভ্যন্তরে absolute zero-copy guarantee দেওয়া হয় না। Filter-এর hardware surface model [official source](https://ffmpeg.org/doxygen/trunk/vf__scale__vt_8c_source.html)-এও সংজ্ঞায়িত; local pinned source দিয়ে compatibility যাচাই হয়েছে।

৭ measured pair-এর 3s 4K→1080p test-এ hardware-frame path ধীর ও quality কম ছিল। এটি default/auto-তে promote করা হয়নি। [ফল ও quality tradeoff](PHASE3-RESULTS.md) দেখুন।
