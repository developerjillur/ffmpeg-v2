# Phase 4–7 — সম্পূর্ণ কাজ ও acceptance register

শুরু: ৩ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Frozen baseline **v0.4.0 / 24b2ac6**। Goal সব চার phase; একটি ছোট fixture বা local unit pass দিয়ে পুরো goal complete হবে না।

## Phase 4 — Performance ও quality

- [x] Publisher/licence/source/checksum-bound দীর্ঘ বাস্তব 1080p ও 4K corpus; synthetic/upscaled footage দিয়ে এই gate পূরণ হবে না।
- [x] Same-machine stock/baseline/candidate stage profiling, codec/filter thread calibration ও hardware scaling comparison।
- [x] একই output contract/quality/validation রেখে repeated paired benchmark-এ বাস্তব improvement; warmup ও uncertainty আলাদা; cold-disk claim নেই।
- [x] Quality regression হলে tuning default-এ promote হবে না; real frame alignment, VMAF/SSIM/PSNR, source/output integrity।

Calibration: [docs/PHASE4-RESULTS.md](docs/PHASE4-RESULTS.md)। শেষ release-এর [comparison](docs/PHASE4-7-RESULTS.md) ও [evidence index](docs/verification/phase4-7-2026-11-03.json) আলাদা।

## Phase 5 — আরও media workflow

- [x] Typed, bounded concat/join: input identities, compatible copy এবং decoded normalization contract, A/V endpoints/frames।
- [x] Subtitle workflow: local allowlisted subtitle/font inputs, escaping, timing, visible text; unsupported combinations explicit।
- [x] Audio mixing: bounded local tracks/gain/timing, channel/rate contract, clipping/finite signal ও actual-content proof।
- [x] প্রয়োজনীয় HDR/image presets: explicit metadata/peak policy ও actual image pixels/colour checks; existing refusal/SDR contract retained।
- [x] CLI/MCP schema, plans, positive/negative fixtures ও independent output validation।

## Phase 6 — বড় job ও দীর্ঘমেয়াদি reliability

- [x] দীর্ঘ বাস্তব batch ও real elapsed-time soak; sampled resource trace ও complete output validation।
- [x] Durable segment checkpoints/recovery: source/tool/spec identities, validated completed segments reuse, final concat/PTS/audio correctness।
- [x] Interrupt/restart/timeout/cancel/disk error tests; successful output ও checkpoints preserved।
- [x] Preemption প্রয়োজন হলে safe segment boundary-তে resumable scheduling; existing priority/aging অপরিবর্তিত রাখা।
- [x] Supervisor/worker failure matrix ও durable receipts; কোন kernel guarantees নেই তা explicit।

## Phase 7 — দৈনন্দিন production ব্যবহার

- [x] বাস্তব স্থানীয় media/agent/CLI consumer inspect ও compatible end-to-end integration; mock-only proof নয়।
- [x] Install/update/rollback lifecycle: isolated candidate, identity/acceptance gate, retained previous selection, actual smoke ও recovery।
- [x] Broader format corpus ও external-sample FATE: acquired files/checksums, enabled-target coverage/failures; whole-suite claim শুধু পুরো coverage প্রমাণ হলে।
- [x] Everyday workflow sample → queue → worker → output → validation → retry/update/rollback সম্পূর্ণ acceptance।
- [x] Final report, evidence index, local release/checkpoint ও requirement-by-requirement completion audit।

প্রতিটি phase-এর implementation ও actual evidence এই register-এ link হবে। Scope/acceptance অমীমাংসিত থাকলে goal active থাকবে। Scoped owner RAM waiver task jobs-এ বহাল; native default, 12 GiB job footprint, disk/mount/time/output checks ও sequential heavy-job policy retained। বড় media/build/cache শুধু project/NexaWork-এ; unrelated apps ও T7 originals untouched।

## সম্পন্ন gates-এর original evidence

| Requirement group | Actual evidence | Scope |
|---|---|---|
| Phase 5 — পাঁচটি requirement | `<LAB_ROOT>/ffmpeg-v2-phase5/acceptance-20261103T170237-a40ad38f/report.json`; `.runtime/verification/mcp-pipeline-20261103T170521-c8266143/report.json` | 17 actual media/error cases; typed schema/queue/mix/PCM, canonical-path refusal; source-edit guard regression দুই Python runtime-এ |
| Phase 6 — দীর্ঘ run | `<LAB_ROOT>/ffmpeg-v2-phase6/soak-20261103T095245-df291d41/{report,endpoint-audit}.json`; `batch-20261103T104855-d6511e3a/report.json` | Actual 30-minute elapsed soak, 355 records ও 54,000 frame; তিন real 180s export, 15,120 frame |
| Phase 6 — recovery/failures | `<LAB_ROOT>/ffmpeg-v2-phase6/quick-20261103T170416-3dc3074c/report.json` | 8 cases; corruption/reuse, preemption, continuous audio equality, write denial, publication reconciliation ও worker/supervisor/both-loss/cancel/timeout |
| Phase 7 — existing consumer | `<LAB_ROOT>/ffmpeg-v2-phase7/studio-20261103T105449-e28b36cc/report.json` | Actual Studio export/reused-part equality/tamper refusal; তিন existing source file-এর SHA আবার মেলে; creative approval নয় |
| Phase 7 — compatibility | `<LAB_ROOT>/ffmpeg-v2-phase7/formats-20261103T103514-4f5190b6/{report,source-format-audit}.json`; `<LAB_ROOT>/ffmpeg-v2-external-fate/run-20261103T103724-3e23f378/report.json` | 15 format cases ও 15 selected external FATE targets; full 5,554-target external suite নয় |
| Current code controls | `<LAB_ROOT>/ffmpeg-v2-phase7/unit-20261103T170415-a0260934/report.json` | 126 tests করে Python 3.9.6 ও 3.14.7; runtime package hashes মেলে |

শেষ acceptance সম্পন্ন: **0.5.0-16f948bf021bd8b7**, 45 frozen code/package files ও 38 native/library bindings।

| শেষ gate | Actual evidence |
|---|---|
| Current 5-pair performance | `<LAB_ROOT>/ffmpeg-v2-phase4/acceptance-20261103T170546-0cf42211/{report,analysis}.json`; 72 outputs rehashed, চার profile speed/quality/size pass |
| Actual install/update/rollback | `<LAB_ROOT>/ffmpeg-v2-phase7/lifecycle-20261103T173037-cf4763d8/report.json`; 9 tests; actual rollback-এ 3,600 frames ও retained segments reuse |
| Final source controls | `<LAB_ROOT>/ffmpeg-v2-phase7/unit-20261103T173058-25432940/report.json`; দুই runtime-এ 126 tests করে; default-policy controls task waiver থেকে isolated |
| Installed configured MCP | `.runtime/verification/mcp-pipeline-20261103T173221-9db290f1/report.json`; server 0.5.0, existing command/roots, PCM/mix/replay/priority/cancel ও refusals |
| Currently connected tools | `.runtime/verification/connected-mcp-20261103T172752-54caad80/independent-audit.json`; actual tool queue/start/status ও independently bit-exact PCM |
| Installed calibrated CLI | `<LAB_ROOT>/ffmpeg-v2-phase4/default-cli-20261103T173250-5f4a7b43/report.json`; চার default profile approved output SHA match |
| Installed real consumer | `<LAB_ROOT>/ffmpeg-v2-phase7/studio-20261103T173417-2f7525e3/report.json`; installed exec→Studio, reused parts equality ও tamper refusal; existing source assets reused |
| Final report/index | [Complete report](docs/PHASE4-7-RESULTS.md), [portable index](docs/verification/phase4-7-2026-11-03.json) |

চার phase-এর 19টি requirement-এর শেষ live-state audit ও Git/tag receipt: `<LAB_ROOT>/ffmpeg-v2-phase7/completion-audit-v0.5.0.json`। Historical failed/interrupted diagnostics retained; final acceptance সেগুলোকে successful proof হিসেবে ব্যবহার করে না।
