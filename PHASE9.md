# Phase 9 — একই tuning-এ HD ও raw-input gap

Maintainer: **Jillur Rahman**। শুরু ৪ নভেম্বর ২০২৬। Baseline `v0.6.0 / a8e44c8a725eb20279072654e5f5a35b7e961a8e`। Installed frozen 0.6.0 candidate acceptance-এর আগে বহাল।

- [x] Phase 8-এর exact input/argv/binary/library/SDK provenance পুনরায় যাচাই; HD +9.53% ও raw +4.44% result ও uncertainty সংরক্ষণ।
- [x] একই codec/filter/decoder/validation settings-এ balanced adjacent comparisons; wall/user/system CPU, faults, I/O/context-switch evidence এবং excluded diagnostic instrumentation।
- [ ] Raw packet/frame feed, redundant filter/copy, build/runtime CPU dispatch ও scheduling আলাদা করে কারণ স্থানীয়করণ। Stock executable fallback দিয়ে ফল বদলানো হবে না।
- [ ] Measured কারণ অনুযায়ী bounded implementation; original inputs, validated publication, guards, explicit caller settings এবং supported media behaviour বজায় রাখা।
- [ ] আলাদা confirmation-এ 60s HD ও retained 30s raw reference, same-tuning Stock এবং frozen 0.6.0 controls; all-frame quality/size ও full decode/hash/frame/audio acceptance।
- [ ] Source/installed CLI/MCP, non-target regression, immutable update/rollback, final comparison ও local source/tag/audit।

আগের full HD interval 0.979218–1.315438; raw control 1.001246–1.107448। নির্দিষ্ট C regression হিসেবে ধরে ফল বানানো যাবে না। Calibration ও confirmation আলাদা হবে; slow trials retained। Same-tuning comparison-এ codec thread counts/preset/CRF/scaler/audio contract দুপাশে এক রাখতে হবে। New feed implementation-এর equivalent Stock control-ও প্রকাশ করতে হবে।

Quality gates পূর্বের মতো: ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05dB, ΔSSIM≥−0.00001, size≤1.02×; exact same encoded SHA হলে একই source/range/fps/model-এর quality reuse করা যাবে। Speed promotion-এর জন্য same Native engine-এর frozen workflow থেকে faster median/paired 95% upper<1 প্রয়োজন। Stock gap closed দাবি করতে target-এর median ratio≤1 এবং independent paired 95% upper≤1.02 প্রয়োজন; uncertainty থাকলে স্পষ্ট রাখতে হবে।

প্রথম bounded diagnostics-এ existing 2.61GiB raw ও publisher sources reused; সম্ভাব্য job peak 2GiB, নতুন scratch ≤4GiB। বড় build কেবল measured native-code/build কারণ থাকলে; আলাদা resource estimate ও sequential work। Task-এর আগের explicit RAM waiver invocation-scoped; sampled 12GiB job, disk/mount/time/output safeguards বহাল। Boot disk এখন 384.8GB used/109.6GB free; নতুন বড় data শুধু mounted `<LAB_ROOT>/ffmpeg-v2-phase9`-এ। Unrelated apps/services বন্ধ হবে না।

অতিরিক্ত queue build/cache clone, lookahead study ও independent controls-এর জন্য scratch estimate **8GiB**; per-job estimate 2GiB, existing sampled hard limit 12GiB। ৪ নভেম্বর মাপে scratch প্রায় 4.02GiB ছিল; source raw বাইরে retained Phase 8 directory-তেই আছে। Boot disk-এ নতুন media/cache রাখা হয়নি।

প্রথম দুই investigation gate সম্পন্ন। Queue capacity ও lookahead-এর দুটি বাস্তব implementation আলাদা checkout-এ compile/run হয়েছে; কোনোটিকে গ্রহণযোগ্য performance fix বলা হয়নি। Native queue 16-এর interval equality পার করে। HD lookahead candidate-এর calibration −8.85% independent full workflow-এ উল্টে **+39.94%** হয়েছে; frozen Native control 13.0545s, candidate 18.2682s, paired 95% ratio 1.1583–1.6227। 1,800-frame quality gates pass, তবু speed gate fail। Active 0.6.0 অপরিবর্তিত; candidate patches শুধু experiments-এ। বাকি checkbox-গুলো verified faster release-এর শর্ত; পরীক্ষাগুলো চলা বা quality pass-কে ওই শর্ত পূরণ ধরা হবে না।

শেষ same-tuning unchanged-default control: HD complete workflow Native 20.253467s বনাম Stock 18.729960s, **+8.13%**, whole-block interval 1.002463–1.095704। Independent raw Native 7.931870s বনাম Stock 7.477305s, **+6.08%**, interval 0.998554–1.277643। Production bytes unchanged; gap fix দাবি করা যায় না। Investigation/audit complete, **Phase 9 performance objective অসম্পূর্ণ**। [সম্পূর্ণ ফল](docs/PHASE9-RESULTS.md), [verification index](docs/verification/phase9-2026-11-04.json)।
