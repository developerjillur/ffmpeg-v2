# MCP ও CLI contract

FFmpeg-v2 newline-delimited stdio JSON-RPC server। stdout শুধু protocol; diagnostics stderr/private receipts-এ। Python 3.9+। বর্তমান 0.6.0/Phase 8 গ্রহণযোগ্যতা [register](../PHASE8.md)-এ; আগের broader gates [Phase 4–7](../PHASE4-7.md)-এ retained।

~~~sh
ffv2 --input-root '/absolute/local/media-root' mcp
~~~

Global flags subcommand-এর আগে দিন। Default MCP read root এই project। এই computer-এর local client entry project ও <LAB_ROOT>/ffmpeg-v2 read roots নেয়। নতুন media root প্রয়োজন হলে explicit --input-root দিন। CLI probe/run local files পড়তে পারে; MCP read allowlist আলাদা।

| Tool | কাজ |
| --- | --- |
| ffv2_doctor | Native/installed capability, current policy ও admission; encode শুরু করে না |
| ffv2_probe | অনুমোদিত input-এর bounded metadata |
| ffv2_plan | Typed spec, exact argv, expected contract, warning ও estimates |
| ffv2_submit | Idempotent durable queue; worker আলাদা |
| ffv2_worker_start | Explicit sequential worker spawn; job status poll করতে হয় |
| ffv2_job_status | State, progress, typed error ও receipt |
| ffv2_job_cancel | Queued/running job cancellation; own process, retained partial |
| ffv2_job_retry | Failed/stopped job-এর নতুন attempt; একই release/identity-তে validated checkpoint reuse |

Initialization এবং notifications/initialized-এর পরে tools/list বা tools/call। Supported protocol versions 2024-11-05, 2025-03-26, 2025-06-18 ও 2025-11-25। Unknown revision-এ supported version negotiation হয়; সব future MCP feature দাবি নেই।

Typed spec schema planner থেকে আসে। Unknown fields, raw argv/filtergraph, bad types, nonfinite times, root violations ও overwrite attempts refuse হয়। outputSchema object; tool failure content/isError-এ, protocol failure JSON-RPC error-এ। Request সর্বোচ্চ 1 MiB; metadata/log/progress bounded।

Phase 2-এর field-ও একই schema-তে আছে: `sampling=auto|single_pass|seek`, `deinterlace=off|bwdif`, `hdr_policy=reject|tone_map`, `source_peak_nits`। Tone map এখন explicit known PQ/HLG থেকে SDR transcode-এর জন্য; missing metadata/dynamic HDR refuse হয়। Explicit VideoToolbox decode hardware frames দিয়ে যাচাই হয়। নতুন field invalid operation-এ ব্যবহার করলে typed refusal পাওয়া যায়। [উদাহরণ](../examples/) ও [policy](PHASE2-DESIGN.md) দেখুন।

Phase 3-তে সব media spec-এ `priority=-10..10` (default 0), এবং transcode-এ `filter_backend=software|videotoolbox` (default software) আছে। Priority/aging-সহ real submit→worker→status→PCM এবং urgent-first receipt পরীক্ষা হয়েছে। Hardware-frame scaler explicit 8-bit SDR/VideoToolbox contract-এর মধ্যে; short fixture-এ measured tradeoff-এর কারণে auto/default নয়। [Phase 3 design](PHASE3-DESIGN.md) ও [ফল](PHASE3-RESULTS.md)।

Phase 4–6-এ independent `decoder_threads`, `filter_threads`, `validation_threads`; typed `concat`, `subtitle`, `audio_mix`, `image`; এবং CFR transcode-এর `checkpoint_seconds` আছে। মোট ৯টি operation, tool inventory ৮টিই থাকে। Nested `tracks` ও `additional_inputs`-ও bounded schema মেনে চলে। Subtitle/font/mix source-এ একই session input-root policy লাগে। [Contract](PHASE5-7-DESIGN.md) ও [examples](../examples/) দেখুন।

Phase 8-এ explicit `encoder=software` transcode-এর `threads` সর্বোচ্চ ৮ এবং `validation_threads` সর্বোচ্চ ৮। Decoder/filter সর্বোচ্চ ৪; encoder+decoder+filter+audio nominal budget সর্বোচ্চ ১৪। বড় encoder pool-এ `threads=8, decoder_threads=2, filter_threads=2, validation_threads=8` একটি valid request। Hardware/অন্য operation-এ encoder threads>4 এবং over-budget combination refused। Validation আলাদা phase-এ চলে; এই budget exact OS thread count নয়।

পরীক্ষিত M4 Max HD native-geometry quality profile-এ pool fields না দিলে 8/2/2/8 auto tuning হতে পারে। Explicit native fps, ≥60s, progressive 8-bit H.264/VP8 ও অন্য scoped conditions [Phase 8 research](PHASE8-RESEARCH.md)-এ আছে। Existing explicit pools, 4K/resize, bitrate, checkpoint ও অন্য presets-এর behaviour বহাল। [Software HD example](../examples/transcode-software-hd.json)-এ paths ও source fps বদলান।

`ffv2_worker_start`-এর explicit `ignore_system_memory=true` শুধু সেই worker-এ owner waiver প্রয়োগ করে। Server startup বা সাধারণ invocation-এ default memory policy বদলায় না। Disk/mount, timeout, output ও sampled job-footprint checks বহাল থাকে।

Installed release বদলালে পুরোনো server-এর planning/submit/retry/worker start `release_changed` দিয়ে থামে; নতুন connection লাগে। পুরোনো job-এর read-only status/cancel দেখা যায়। Cross-release checkpoint retry-তে `runtime_code_changed` হলে matching retained release-এ rollback অথবা নতুন plan বেছে নিতে হবে।

Mutable source server startup-এর workflow digest ধরে রাখে। Source edit হওয়ার পরে probe/plan/submit/retry/start `runtime_code_changed` পায়; নতুন connection লাগে। Canonical path-এর newline/CR alias দিয়েও গ্রহণ হয় না। এই refusal fresh stdio ও controlled source-edit regression-এ পরীক্ষা করা হয়।

Recommended flow: doctor → probe → plan → submit with stable idempotency_key → worker_start → poll job_status → consume only completed receipt/output hash। Launch response spawned_not_verified; encoding success নয়। Terminal failure-এর পরে নতুন key পাঠিয়ে blind retry করবেন না; original job/receipt দেখে explicit retry করুন।

Generic client configuration [examples/mcp.config.json](../examples/mcp.config.json)-এ। এই computer-এর global local-client entry ffmpeg-v2 যোগ হয়েছে; অন্য settings সংরক্ষিত ও private backup আছে। Configured entry, stdio round trip এবং running chat tool inventory আলাদা প্রমাণ। Current chat hot reload দাবি নেই; নতুন session দিয়ে client tools load করা যায়। [Official local MCP configuration](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)।

Real verifier: scripts/verify_mcp_pipeline.py। Native fork-এর সঙ্গে initialize/list/doctor/probe/plan, submit/replay, actual background worker, completed checksum/bit-exact PCM, denied input, unknown field ও queued cancel পাস করেছে। CLI verifier scripts/verify_control_plane.py-ও active engine দিয়ে nonzero PCM export ও replay পাস করেছে।

Default server startup কাজ শুরু করে না। Current task-এর RAM waiver testing invocation-এ scoped ছিল; installed client configuration-এ স্থায়ী ignore flag যোগ করা হয়নি।
