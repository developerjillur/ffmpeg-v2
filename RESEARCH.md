# গবেষণা ও সিদ্ধান্ত

২ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**।

## স্থানীয় evidence

Source/workspace inspection-এ এই folder শুরুতে খালি ছিল; parent-এর unrelated projects অক্ষুণ্ণ। Mac16,9 Apple M4 Max, arm64, 36 GiB, 10P+4E। Installed FFmpeg/ffprobe 9.0.2। Codec-library build, VideoToolbox, AudioToolbox, NEON ও libvmaf capabilities live query করা হয়েছে; পরে actual sessions-ও পরীক্ষা হয়েছে।

../context_worker/engine.py-এর media probe এবং frame loop (প্রায় 397, 500, 516)-এ প্রতি timestamp-এর জন্য আলাদা process পাওয়া যায়। Actual source PTS রাখার pattern বজায় রেখে dense-window single-pass contact sheet যোগ করা হয়েছে। এটি existing production worker নিজে বদলায়নি; fixture migration comparison timestamps সমান পেয়েছে, median pipeline ratio 14.11×।

Small 4s 640×360 fixture-এ libx264 encode 0.143s এবং VideoToolbox 0.273s ছিল। তাই small clip-এ hardware listing-কে fastest ধরে নেওয়া হয়নি; auto selection ওই bounded clip class-এ software নেয়। বড় 720p fixture-এ repeated timing আছে; broad/causal core speed claim নেই।

Upstream key/value progress machine-readable হলেও agent client-এর native JSON line চাহিদা আলাদা। Minimal optional C extension যোগ হয়েছে; default compatibility বহাল। Source patch একটি interface enhancement; encoder algorithm acceleration দাবি নয়।

## প্রথম পক্ষের উৎস

| Source | সিদ্ধান্তে প্রভাব |
| --- | --- |
| [FFmpeg CLI](https://ffmpeg.org/ffmpeg.html) | Stream copy, native progress, explicit thread/codec flags, hardware runtime যাচাই |
| [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html) | select/tile/showinfo, libvmaf/SSIM ও framesync alignment |
| [Official source](https://github.com/FFmpeg/FFmpeg) | n9.0.2 tag/peeled commit; native patch ও FATE implementation |
| [FATE](https://ffmpeg.org/fate.html) | Local generated tests বনাম external-sample coverage |
| [Security](https://ffmpeg.org/security.html) | Source pin-এর সঙ্গে future security refresh রাখতে হবে |
| [Licence](https://ffmpeg.org/legal.html) | GPL/version3 configuration, source correspondence ও third-party notices |
| [MCP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | Newline JSON-RPC, protocol-only stdout |
| [MCP lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle) | Version negotiation, initialize/ready flow |
| [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools) | Typed schemas, structured results ও tool/protocol errors |
| [Apple libproc source](https://github.com/apple-oss-distributions/xnu/blob/main/libsyscall/wrappers/libproc/libproc.c) ও local SDK | proc_pid_rusage/physical footprint measurement |
| [Local MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) | stdio configuration; configured entry ও loaded chat tools আলাদা |

Exact lock ও source provenance [UPSTREAM.md](docs/UPSTREAM.md)-এ। Benchmark quality প্রথম pass-এ container timebase mismatch ধরা পড়ে; outputs পুনর্ব্যবহার করে 180 decoded frame align করে সংশোধিত score নেওয়া হয়। এই সংশোধন ছাড়া পুরোনো score release evidence হিসেবে গ্রহণ করা হয়নি।

## সিদ্ধান্ত ও সীমা

Default sequential worker, 2 default/4 maximum codec threads, 12 GiB sampled job cap; সব বড় data external project/NexaWork-এ। Owner-এর সর্বশেষ নির্দেশে current goal-এর RAM/pressure stop explicitভাবে ignored; পূর্বের refusal stage ঐতিহাসিক। Disk/mount/source/output safeguards বহাল।

4K SDR Main10 hardware path ও 600s synthetic timeline পাস। Private/representative corpus, HDR tone mapping, VFR/interlaced colour matrix, perceptual long-form sync এবং long wall-clock soak এখনও পৃথক গবেষণা। Production worker migration ও public release স্থানীয় test থেকে inferred হয়নি। [GAPS.md](docs/GAPS.md), [VALIDATION.md](docs/VALIDATION.md)।
