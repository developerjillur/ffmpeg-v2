# Phase 4 research ও predeclared performance gate

৩ নভেম্বর ২০২৬। Maintainer: **Jillur Rahman**। Baseline v0.4.0/24b2ac6 frozen checkout NexaWork-এ। Scope: Phase 4–7 goal অপরিবর্তিত।

## Corpus ও publisher evidence

- [Big Buck Bunny official licence](https://peach.blender.org/about/): CC BY 3.0; attribution `(c) copyright 2008, Blender Foundation / www.bigbuckbunny.org`। [Official distribution](https://download.blender.org/demo/movies/BBB/) থেকে Sunflower 30fps normal 1080p ও 2160p ZIP; publisher index sizes 275,524,128 ও 632,204,510 bytes। এগুলো rendered production film, testsrc বা upscaled fixture নয়। Observed dimensions/duration acquisition receipt যাচাই করবে; publisher-signed SHA পাওয়া যায়নি, observed HTTPS SHA-256 আলাদা label পাবে।
- [Tears of Steel official licence](https://mango.blender.org/about/): CC BY 3.0; [Xiph publisher corpus README](https://media.xiph.org/tearsofsteel/README.txt) একই licence ও Blender attribution দেয়। Live-action/VFX 1080p WebM [source](https://media.xiph.org/tearsofsteel/tears_of_steel_1080p.webm)। Blender directory-এর `copyright.txt` Original Soundtrack-এর BY-ND notice; film-এর licence হিসেবে সেটি ব্যবহার করা হবে না।
- [Netflix Open Content](https://opencontent.netflix.com/) CC BY 4.0 real HDR corpus দেয়। Public S3 listing-এ Chimera DCI4K23.98 PQ/P3 MP4 2,533,440,911 bytes; 59.94 version >10GB হওয়ায় bounded next-test corpus হিসেবে নেওয়া হয়নি। HTTPS dotted virtual-host certificate mismatch হলে certificate verification disable নয়; official path-style S3 endpoint দিয়ে metadata পাওয়া যায়। HDR/P3 policy Phase 5-এর explicit compatibility/quality gate।

Movie files ও derivatives private QA corpus; original full movies/credits retained। Software authorship ও third-party footage attribution পৃথক। Acquisition archive CRC/size, file SHA-256, native dimensions, >120s duration, system/disk/job bounds ও resumable object identity পরীক্ষা করে।

## Technical evidence ও সিদ্ধান্ত

Pinned source `doc/ffmpeg.texi`-এর `filter_threads` প্রতি pipeline-এর thread pool নিয়ন্ত্রণ করে। Default পুরো CPU count; existing wrapper decoder/encoder=2 ও filter≤2 দিয়ে oversubscription কমিয়েছে। Phase 4 প্রথমে explicit 2/4 codec-thread calibration করবে; total concurrent heavy process sequential থাকবে। Source/codec/config/decoded-frame alignment ছাড়া speed comparison গ্রহণযোগ্য হবে না।

Pinned `vf_scale_vt.c` hardware frames ও VTPixelTransferSession ব্যবহার করে; source-এ explicit high-speed option নেই। Phase 3-এর short synthetic loss দেখে hardware path default হয়নি। Longer natural corpus-এ same bitrate/geometry ও common-reference quality দিয়ে পুনরায় বিচার হবে; negative result-ও report-এ থাকবে।

প্রস্তাবিত software promotion threshold আগেই নির্ধারিত: repeated paired full-job median কমবে; quality delta baseline-এর তুলনায় VMAF ≥−0.10, PSNR-Y ≥−0.05dB, SSIM ≥−0.00001; file-size increase ≤2%। Frame count/range/audio endpoints/metadata/full strict decode/hash/publish সব pass প্রয়োজন। Threshold বা workload ফল দেখার পরে সুবিধামতো বদলানো হবে না। Hardware preset এই gate না পেরোলে explicit option থাকবে, default নয়।

## Current consumer ও পরের phases

Existing `context_worker/engine.py` real frame/source-PTS workflow-তে ffprobe/ffmpeg চালায়। Studio timeline/faceless modules concat/audio/subtitle-related transforms চালায়। Phase 7-এ implementation edit-এর আগে exact consumer contract, test setup ও active jobs দেখা হবে; isolated smoke-কে live integration বলা হবে না।

Native build tests/Makefile external FATE `SAMPLES` দিলে enabled external targets যুক্ত করে এবং `fate-rsync` publisher sync দেয়। Phase 7-এ bounded sample acquisition/coverage manifest প্রয়োজন; local 2,893 tests-কে external coverage হিসেবে পুনরায় label করা হবে না।
