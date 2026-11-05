# উৎস ও লাইসেন্স

Workflow, CLI, MCP interface এবং local patch-এর maintainer: **Jillur Rahman**। এই repository-র নিজস্ব code GPL-3.0-or-later; [LICENSE](LICENSE) দেখুন।

FFmpeg core upstream-এর copyright এবং licence বজায় রাখে। Local fork-এর ভিত্তি n9.0.2, commit 946fcce07b6dcd0331c8cc609192aeff5e1924f8। Core source-এর COPYING.*, LICENSE.md, file notices এবং Git history অক্ষুণ্ণ। Core source external workspace-এ; repository-তে exported patch ও source lock আছে। কোনো upstream acceptance বা affiliation দাবি করা হচ্ছে না।

এই computer-এর M4 build --enable-gpl --enable-version3 ব্যবহার করে। Codec libraries-এর মধ্যে x264, x265, SVT-AV1, libvpx, dav1d, libopus, libmp3lame, libvmaf ও OpenSSL আছে; সেগুলোর নিজস্ব copyright/licence source installation-এ থাকে। Activation receipt binary এবং non-system dylib dependency closure-এর SHA-256 রাখে। Homebrew library upgrade হলে selection stale হয়ে যায়; নতুন acceptance প্রয়োজন।

Build prerequisite pkgconf 3.0.10 Ariadne-এর official source থেকে checksum মিলিয়ে আলাদা local prefix-এ build করা হয়েছে। এর ISC licence source-এর COPYING-এ আছে। Python workflow-এ তৃতীয় পক্ষের runtime package প্রয়োজন নেই।

Phase 2-তে static zimg 3.0.6 যুক্ত হয়েছে। Official Homebrew bottle ও source SHA-256 bootstrap script-এ pinned; project-specific static archive global installation বদলায় না। Original WTFPL v2 licence [third_party/zimg/COPYING](third_party/zimg/COPYING)-এ অক্ষুণ্ণ রাখা হয়েছে। ffplay existing SDL2 ব্যবহার করে; [SDL2 licence](https://github.com/libsdl-org/SDL/blob/SDL2/LICENSE.txt) এবং installed library-এর notices প্রযোজ্য।

Phase 5-তে private static libass 0.17.5 যুক্ত হয়েছে। Official archive SHA-256 `caab4b993dd7be6187c55623b789ed75dddefea6e65938af134637c732fe094a`; bootstrap [script](scripts/bootstrap_libass.py)-এ source ও bound আছে। Original ISC notice [third_party/libass/COPYING](third_party/libass/COPYING)-এ অক্ষুণ্ণ। Existing FreeType, HarfBuzz ও FriBidi-এর নিজস্ব licence প্রযোজ্য; কোনো global Homebrew package বদলানো হয়নি। macOS CoreText ও system fonts স্থানীয় rendering-এ ব্যবহৃত; system font এই repository-তে বিতরণ করা হয়নি।

Phase 10-এর experimental private x264 official [VideoLAN source](https://code.videolan.org/videolan/x264) revision `b35605ace3ddf7c1a5d67a2eb553f034aef41d55` থেকে build হয়েছে। Original GPL-2.0-or-later [COPYING](third_party/x264/COPYING), source/patch [manifest](third_party/x264/manifest.json), দুই local patch ও [build notes](third_party/x264/README.md) retained। Local progress-query patch-এর maintainer Jillur Rahman। Private binary আলাদা staged prefix-এ; active release এবং public distribution acceptance-এর অবস্থা Phase 10 results-এ আলাদা করে দেওয়া আছে। Upstream-এর copyright ও corresponding-source obligations বহাল।

Phase 4-এর Big Buck Bunny ও Tears of Steel publisher corpus, attribution, licence, URL ও acquisition checksum [research record](docs/PHASE4-RESEARCH.md)-এ আছে। Test media ও derived outputs local external workspace-এ থাকে; tracked source release-এ নেই। Publisher HDR excerpt-এর metadata-অনুপস্থিত negative test ও selected external FATE samples-এর individual acquisition receipts-ও retained। Observed sample SHA-256-কে publisher-signed checksum বলা হয় না।

Xiph-এর Akiyo/Bus raw test footage private runtime directory-তে QA-এর জন্য থাকে, tracked source বা public deliverable-এ নয়। [Collection-এর copyright context](https://media.xiph.org/video/derf/) এবং প্রতিটি source URL/checksum test receipt-এ রাখা হয়; collection-এর সব clip-এর জন্য নতুন unrestricted licence দাবি করা হয় না।

Binary/source redistribution-এর আগে exact build configuration, corresponding source, applied patches এবং dependency licence obligations একসঙ্গে মিলিয়ে নিতে হবে। এই কাজের receipts local verification; public distribution বা hosted release হয়নি।

প্রথম পক্ষের reference: [FFmpeg legal](https://ffmpeg.org/legal.html), [FFmpeg source](https://github.com/FFmpeg/FFmpeg), [pkgconf source](https://github.com/pkgconf/pkgconf)।
