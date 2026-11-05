# Third-party source and license notices

FFmpeg-v2 toolkit and original modifications: Jillur Rahman, GPL-3.0-or-later;
see [LICENSE](LICENSE). Upstream copyright notices are preserved. This project is
independent of FFmpeg, VideoLAN, Apple, GitHub and the MCP specification maintainers.

| Component | Publication contents | License / provenance |
|---|---|---|
| FFmpeg | Lock file and three optional patches; no full engine binary | [Official source](https://github.com/FFmpeg/FFmpeg), [legal page](https://ffmpeg.org/legal.html), exact base in upstream.lock.json |
| x264 | Two experimental patches and manifests/recipe | GPL-2.0-or-later, [COPYING](third_party/x264/COPYING), [source](https://code.videolan.org/videolan/x264.git) |
| libass | Pinned build recipe and license notice | ISC-style notice in [COPYING](third_party/libass/COPYING) |
| zimg | Pinned build recipe and license notice | WTFPL notice in [COPYING](third_party/zimg/COPYING) |
| marked | Documentation build-time dependency only | MIT, pinned in package-lock.json; upstream license in its package |
| Playwright / axe-core | Development/CI checks only | Apache-2.0 / MPL-2.0, pinned in package-lock.json; upstream package notices retained by npm |

The historical corpus references Big Buck Bunny and Tears of Steel from Blender's
open-movie projects. Media is not bundled. Obtain any source from its original
publisher and follow its attribution/license terms independently. Client/private
media, credentials and local profiles are not published.

Source patch distribution does not grant a license for unrelated linked libraries.
If you distribute a binary built with optional codecs or features, review that
binary's full dependency closure and fulfill applicable source/license obligations.
