# Phase 3 — software pipeline ও বাকি operational gaps

শুরু: **৩ নভেম্বর ২০২৬**। Maintainer: **Jillur Rahman**। Baseline **v0.3.0 / d3128af** অক্ষুণ্ণ রাখা হয়েছে।

## কাজ ও গ্রহণযোগ্যতা

- [x] Stock/native stage profile, ১৫-trial pipeline ও পৃথক ৯-trial actual CLI comparison; uncertainty প্রকাশ।
- [x] Explicit custom binaries-এর dependency-verified cache; OS/ctime/load-path/corruption invalidation ও cold hash-race check।
- [x] Native resource API ও empty-selector wait fix; strict full decode/metadata/hash/no-clobber বহাল।
- [x] Supported hardware-frame scaling বাস্তবে পরীক্ষা; measured slowdown/quality loss-এর কারণে default promotion প্রত্যাখ্যাত, explicit option retained।
- [x] Durable priority/aging, additive legacy migration ও nonce/birth-identity supervisor-loss recovery।
- [x] 102 control tests দুই Python runtime-এ, 32 actual checks, exact output proof, report ও স্থানীয় 0.4.0 checkpoint।

Same-engine native pipeline median −21.44%, actual CLI process −17.75%। Stock/native stable advantage unresolved: matched pipeline +3.31% native time, পৃথক actual CLI −3.41%; interval equality পার করে। 9.3% historical regression universally শূন্য হয়েছে এমন দাবি নেই। [পূর্ণ comparison](docs/PHASE3-RESULTS.md), [implementation](docs/PHASE3-DESIGN.md) ও [proof](docs/verification/phase3-2026-11-03.json)।

পূর্বের scoped RAM/pressure override এই task-এর runs-এ বহাল। Heavy local jobs sequential; job footprint, disk/mount, output/time checks থাকে। Source/cache/results NexaWork/project-এ; unrelated apps বন্ধ করা হয় না।

প্রতিটি closure actual evidence অনুযায়ী লেখা হবে। Private HDR display judgement, overnight reliability, full external FATE ও kernel-level all-process-kill guarantee আলাদা acceptance; সেগুলো ছাড়া universal closure দাবি হবে না।
