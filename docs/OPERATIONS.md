# দৈনন্দিন ব্যবহার, update ও recovery

Maintainer: **Jillur Rahman**। সব command স্থানীয়; public push বা hosted deployment নয়। Current release ও acceptance [STATUS.md](../STATUS.md)-এ।

## কাজের স্বাভাবিক পথ

~~~sh
ffv2 --version
ffv2 release status
ffv2 doctor
ffv2 probe '/absolute/path/input.mp4'
ffv2 plan '/absolute/path/job.json'
ffv2 submit '/absolute/path/job.json' --key export-20261103-001
ffv2 worker --drain
ffv2 status JOB_ID --events
~~~

Output এই project অথবা mounted `<LAB_ROOT>`-এর মধ্যে দিন; output directory আগে তৈরি করুন। `completed` receipt-এর validation ও output SHA-256 মিলে তবেই result ব্যবহার করুন। Submit বা worker-spawn response encoding সফল হওয়ার প্রমাণ নয়। একই request-এর retry-তে প্রথমে original job ID/receipt দেখুন; নতুন key দিয়ে অযথা duplicate encode করবেন না।

Owner-এর explicit RAM waiver প্রয়োজন হলে subcommand-এর আগে `--ignore-system-memory` দিন। এটি শুধু সেই invocation/worker-এর pressure, headroom ও swap stop উপেক্ষা করে। Per-job footprint, disk/mount, timeout ও output safeguards সক্রিয় থাকে। সাধারণ command ও MCP startup-এর default policy অপরিবর্তিত।

দীর্ঘ HD software quality export-এর জন্য [software HD example](../examples/transcode-software-hd.json) ব্যবহার করুন: নিজের paths, source-এর native integer `fps` ও valid range দিন। `encoder=software`, `rate_control=quality` এবং pool fields বাদ রাখলে matching M4 Max profile নতুন 8/2/2/8 tuning নেয়। `ffv2 plan`-এর `runtime_tuning` দেখে profile ও budget নিশ্চিত করুন। Source যদি 24fps হয়, উদাহরণের 30 বদলে 24 দিন; frame-rate conversion দ্রুততার এই profile-এর scope নয়।

Explicit pools প্রয়োজন হলে software transcode-এ `threads=8`, `decoder_threads=2`, `filter_threads=2`, `validation_threads=8` দেওয়া যায়। বড় encoder pool-এর সঙ্গে legacy বড় decoder pool রেখে total budget ছাড়ালে `thread_budget_exceeded` হবে। Caller-এর explicit pool settings auto profile বদলায় না। 4K/resize, checkpoint, bitrate, HDR/deinterlace/hardware ও অন্য CPU-তে এই নতুন tuning স্বয়ংক্রিয়ভাবে ব্যবহার হয় না। [সম্পূর্ণ eligibility](PHASE8-RESEARCH.md)।

`ffmpeg-v2`, `ffprobe-v2`, `ffplay-v2` installed release-এর pinned native programs-এর পূর্ণ CLI। এই সরাসরি command-গুলোর process lifecycle caller পরিচালনা করে। Existing local program-এর `ffmpeg` lookup-ও pinned ও supervised করতে:

~~~sh
ffv2 exec --work-dir '<LAB_ROOT>/my-export' --timeout 1800 -- python3 '/absolute/path/export_worker.py'
~~~

এটি trusted CLI execution। Arbitrary command MCP থেকে চালানো যায় না। Consumer-এর নিজস্ব output overwrite policy আগে দেখুন; wrapper তার semantic validation-এর বিকল্প নয়। Existing Studio timeline worker-এর technical acceptance source না বদলিয়েই এই পথে হয়েছে।

## Checkpoint ও interruption

দীর্ঘ zero-origin CFR source-এ [checkpoint example](../examples/checkpoint.json) ব্যবহার করা যায়। Explicit fps source-এর native integer fps-এর সমান রাখুন; range frame grid-এ মিলতে হবে। VFR/nonzero-origin source-এর সাধারণ transcode সমর্থিত হলেও এই checkpoint preset সমর্থন করে না।

~~~sh
ffv2 cancel JOB_ID
ffv2 status JOB_ID --events
ffv2 retry JOB_ID
ffv2 worker --job-id JOB_ID
~~~

Retry একই code/source/engine/spec-এর validated segments reuse করে; চলমান partial segment থেকে append করে না। Corrupt segment rebuild হয়, সফল segment ও original diagnostic evidence retained থাকে। Source বদলালে নতুন plan দিন। Filesystem denial ঠিক হওয়ার পরে explicit retry করা যায়। Engine/library identity বদলালে acceptance ও activation আগে সম্পন্ন করতে হবে।

## Update ও rollback

Installed runtime source checkout থেকে আলাদা frozen directory-তে থাকে। `.runtime/active-release.json` দিয়ে এক code/engine pair নির্বাচন হয়; queue database একই project-এ থাকে। New release-এর দশটি acceptance gate ও matching package/native hashes ছাড়া install হয় না। Build/acceptance pipeline [UPSTREAM.md](UPSTREAM.md), contract [PHASE5-7-DESIGN.md](PHASE5-7-DESIGN.md)।

~~~sh
ffv2 release status
ffv2 jobs
ffv2 release install --source '/absolute/verified/source' --acceptance '/absolute/completed-acceptance.json'
ffv2 --version
ffv2 doctor
ffv2 release rollback
ffv2 --version
~~~

Queued/running/validating কাজ থাকলে activation থামে; সেগুলো শেষ হতে দিন অথবা উদ্দেশ্য বুঝে explicit cancel করুন। Update নিজে কাজ cancel করে না। `worker_busy` হলে অন্য owned heavy task শেষ হওয়ার পরে আবার চেষ্টা করুন। Failure-এর সময় আগের pointer/manifest অক্ষুণ্ণ থাকে।

Custom `--state-dir` দিয়ে কাজ করলে update/rollback-এর সময়ও একই global flag দিন। Queue fence নির্বাচিত state ও project-এর default state দেখে; shared host lock চলমান media কাজ আটকায়। অন্য custom database স্বয়ংক্রিয়ভাবে scan হয় না। সেখানকার পুরোনো plan নতুন code-এ চালালে code-identity refusal হয়; matching release-এ rollback করে সেই state-এর কাজ retry করুন।

New release-এর পরে পুরোনো MCP server mutation-এ `release_changed` পেলে নতুন connection শুরু করুন। পুরোনো job-এর status দেখা যায়। Checkpoint retry-তে `runtime_code_changed` হলে সেই job তৈরির retained release-এ rollback করে retry করুন, অথবা নতুন release-এ নতুন plan বানান। Completed old output এবং successful segments মুছতে হয় না। Rollback শেষে desired release-এর retained manifest explicit activate করা যায়:

~~~sh
ffv2 release activate --manifest '/absolute/retained/release.json'
~~~

`release link-launchers` চারটি পরিচিত user-local launcher-ই বদলায়; unrelated file থাকলে refuse করে এবং previous symlink target রাখে। System/Homebrew `ffmpeg` replace করে না।

## Integrity error

`engine_changed`, `binary_changed`, `release_changed` বা `release_launch_failed` উপেক্ষা করে source/manifest edit করবেন না। Binary/library content, mount, symlink ও version পরীক্ষা করুন। Changed filesystem device identity-তেও strict selection থামতে পারে; SHA একই থাকলেও explicit candidate verification ও reactivation প্রয়োজন। Frozen release-এর engine snapshot স্বতঃস্ফূর্তভাবে rewrite হয় না।

`state_unavailable` হলে database রেখে storage/permission/integrity দেখুন। Unrelated services/apps বন্ধ করা, broad temporary-file cleanup বা original media মুছে জায়গা করা এই workflow-এর অংশ নয়। Guardian ও watchdog sampled user-space control; kernel failure, sudden power loss এবং detached third-party service-এর জন্য universal guarantee নয়।

`invalid_input`, `invalid_output` বা `invalid_state`-তে canonical path-এর newline/CR থাকলে স্বাভাবিক নামে নতুন task path ব্যবহার করুন। Alias-এর target-ও পরীক্ষা হয়। Source checkout edit করার পরে existing MCP process-এর `runtime_code_changed` হলে fresh connection নিন; installed release checkout edit-এর সঙ্গে বদলায় না।
