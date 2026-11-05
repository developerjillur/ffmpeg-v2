"""PNG/JPEG/WebP still input; aspect/alpha/bit-depth policy explicit।"""
from __future__ import annotations

import struct
from pathlib import Path

from .advanced import COMMON, fields, finish
from .bindings import strong_identity
from .errors import FFV2Error
from .io import input_path, output_path
from .media import INPUT_LIMITS, probe_path
from .video_policy import video_policy


def reject_animation(path):
    with path.open("rb") as stream:
        header = stream.read(32)
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP" and header[12:16] == b"VP8X" and header[20] & 2:
            raise FFV2Error("image_animation_unsupported", "Animated WebP-এর জন্য animation workflow প্রয়োজন; প্রথম frame নীরবে নেওয়া হয় না।")
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            stream.seek(8)
            for _ in range(128):
                chunk = stream.read(8)
                if len(chunk) != 8:
                    break
                size, name = struct.unpack(">I4s", chunk)
                if name == b"acTL":
                    raise FFV2Error("image_animation_unsupported", "APNG input-এর জন্য animation workflow ব্যবহার করুন।")
                if name in (b"IDAT", b"IEND"):
                    break
                if size > path.stat().st_size - stream.tell() - 4:
                    raise FFV2Error("invalid_image", "PNG chunk length file-এর বাইরে।")
                stream.seek(size + 4, 1)
            else:
                raise FFV2Error("image_header_budget", "PNG metadata chunk budget অতিক্রম করেছে।")


def image_format(request, video):
    suffix = Path(request["output"]).suffix.lower()
    if suffix not in (".png", ".jpg", ".jpeg"):
        raise FFV2Error("invalid_container", "Image output PNG অথবা JPEG হতে হবে।")
    png = suffix == ".png"
    hdr = video.get("color_transfer") in ("smpte2084", "arib-std-b67") or video.get("color_primaries") == "bt2020"
    pixel = video.get("pix_fmt", "")
    source_depth = 16 if any(value in pixel for value in ("48", "64", "16", "10", "12", "14")) else 8
    depth = request.get("image_bit_depth", 16 if hdr else source_depth) if png else 8
    if not png and request.get("image_bit_depth", 8) != 8:
        raise FFV2Error("image_bit_depth_unsupported", "JPEG preset 8-bit; 16-bit output-এর জন্য PNG দিন।")
    if png and ("image_quality" in request or "jpeg_chroma" in request) or not png and "compression_level" in request:
        raise FFV2Error("invalid_spec", "PNG-তে compression_level, JPEG-তে image_quality দিন।")
    alpha = pixel.startswith(("rgba", "bgra", "argb", "abgr", "gbrap", "yuva", "ya")) or pixel == "pal8"
    preserve_alpha = png and alpha and "background" not in request
    fmt = ("rgba64be" if preserve_alpha else "rgb48be") if depth == 16 else ("rgba" if preserve_alpha else "rgb24")
    return {"png": png, "depth": depth, "alpha": preserve_alpha, "pix_fmt": fmt,
            "codec": "png" if png else "mjpeg", "matte": request.get("background", "#000000") if not png or "background" in request else None}


def image_encoder(request, policy):
    if policy["png"]:
        return ["-c:v", "png", "-threads:v", "1", "-pix_fmt", policy["pix_fmt"], "-compression_level", str(request.get("compression_level", 6))]
    pixel = []
    if request["operation"] == "image" or "jpeg_chroma" in request:
        pixel = ["-pix_fmt", "yuvj" + request.get("jpeg_chroma", "444") + "p"]
    return ["-c:v", "mjpeg", "-threads:v", "1", *pixel, "-q:v", str(request.get("image_quality", 3))]


def build_image(request, settings, caps, *, restricted, allow_existing):
    fields(request, COMMON | {"max_width", "max_height", "hdr_policy", "source_peak_nits", "background", "image_bit_depth", "image_quality", "compression_level", "jpeg_chroma"})
    source = input_path(request["input"], settings, restricted=restricted)
    if source.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp") or source.stat().st_size > 256 * 1024**2:
        raise FFV2Error("image_input_unsupported", "Bounded single PNG/JPEG/WebP input দিন।")
    reject_animation(source)
    media = probe_path(source, caps["ffprobe"], image=True)
    video = media["video"]
    if not video or not all(type(video.get(k)) is int and 2 <= video[k] <= 8192 for k in ("width", "height")):
        raise FFV2Error("invalid_dimensions", "Image dimensions গ্রহণযোগ্য নয়।")
    from .planner import dimensions
    width, height = dimensions(video, request.get("max_width", min(video["width"], 3840)), request.get("max_height", min(video["height"], 2160)),
                               even=Path(request['output']).suffix.lower() in ('.jpg','.jpeg') and request.get('jpeg_chroma','444') == '420')
    if width * height > 3840 * 2160:
        raise FFV2Error("output_resolution_budget", "Image preset সর্বোচ্চ 3840×2160 pixel budget।")
    output = output_path(request["output"], source, settings, allow_existing=allow_existing)
    policy = image_format(request, video)
    if policy["codec"] not in caps["encoders"]:
        raise FFV2Error("encoder_missing", "Image encoder build-এ নেই।")
    before, colour, options, colour_expected, warnings = video_policy(request, video, caps)
    argv = [caps["ffmpeg"], "-nostdin", "-hide_banner", "-v", "error", "-n", "-xerror", "-nostats", "-progress", "pipe:1",
            "-filter_threads", "2", "-filter_complex_threads", "2", *INPUT_LIMITS[:-1], INPUT_LIMITS[-1] + ",image2,jpeg_pipe,png_pipe,webp_pipe",
            "-f", "image2", "-pattern_type", "none", "-threads", "1", "-err_detect", "explode", "-i", str(source)]
    chain = before + colour + [f"scale={width}:{height}", "setsar=1"]
    if policy['matte'] and policy['depth'] == 16:
        if 'geq' not in caps['filters']:
            raise FFV2Error('filter_missing', '16-bit alpha matte-এর জন্য geq filter প্রয়োজন।')
        background = [int(policy['matte'][i:i+2],16)*257 for i in (1,3,5)]
        expressions = ':'.join(channel+"='"+channel+'(X,Y)*alpha(X,Y)/65535+'+str(value)+"*(1-alpha(X,Y)/65535)'" for channel,value in zip(('r','g','b'),background))
        chain += ['format=gbrap16le','geq='+expressions+':a=65535']
        argv += ['-map', f"0:{video['index']}", '-vf', ','.join(chain)]
    elif policy["matte"]:
        value = policy["matte"][1:]
        graph = ("[0:v]" + ",".join(chain) + ",format=rgba[foreground];" +
                 f"color=c=0x{value}:s={width}x{height}:r=1,format=rgba[background];" +
                 "[background][foreground]overlay=shortest=1:format=rgb:alpha=straight[image]")
        argv += ["-filter_complex", graph, "-map", "[image]"]
    else:
        argv += ["-map", f"0:{video['index']}", "-vf", ",".join(chain)]
    budget = max(16 * 1024**2, width * height * (4 if policy["alpha"] else 3) * (policy["depth"] // 8) + 4 * 1024**2)
    argv += ["-frames:v", "1", "-an", "-sn", "-dn", *image_encoder(request, policy), *options,
             "-map_metadata", "-1", "-f", "image2", "-update", "1", "-fs", str(budget), "<STAGING_OUTPUT>"]
    plan = {"schema_version": 1, "source": media, "spec": {"output": str(output)},
            "binary": {key: caps[key] for key in ("ffmpeg", "ffprobe", "ffmpeg_version", "ffprobe_version", "ffmpeg_identity", "ffprobe_identity")},
            "encoder": policy["codec"], "argv": argv, "expected": {"duration_seconds": 0, "video_codec": policy["codec"], "audio_codec": None,
                "video_streams": 1, "audio_streams": 0, "width": width, "height": height, "video_frames": 1, **colour_expected},
            "timeout_seconds": request.get("timeout_seconds", 120), "hardware_runtime_verified": None, "warnings": warnings,
            "estimates": {"job_memory_bytes": int(0.5 * 1024**3 + video["width"] * video["height"] * 64), "output_budget_bytes": budget,
                          "method": "bounded still-image buffers and optional float HDR transform"},
            "runtime_tuning": {"validation_threads": request.get("validation_threads", 2), "profile": "single_image"}}
    if caps.get("engine_selection_id"):
        plan["binary"]["engine_selection_id"] = caps["engine_selection_id"]
    if caps.get("runtime_binding"):
        plan["binary"]["runtime_binding"] = caps["runtime_binding"]
    media["strong_identity"] = strong_identity(source)
    if not policy["png"]:
        plan["warnings"].append("JPEG is 8-bit; selected chroma sampling ও requested/default black background-এ alpha flatten হয়।")
    return finish(plan, request, settings)
