"""Codec/filter/validation pools আলাদা; measured policy-ই default হতে পারে।"""
from __future__ import annotations

from .errors import FFV2Error

M4_LONG_PROFILE_ENABLED = True


def pools(request, video, duration, caps, *, width=None, height=None):
    from .media import rational
    legacy = request.get("threads", 2)
    encoder, decoder, filters, validation = legacy, legacy, min(legacy, 2), 2
    profile = "explicit" if "threads" in request else "conservative"
    width, height = width or int((video or {}).get("width", 0)), height or int((video or {}).get("height", 0))
    source_fps = rational((video or {}).get("avg_frame_rate"))
    eligible = (M4_LONG_PROFILE_ENABLED and "threads" not in request and request["operation"] == "transcode" and
                request.get("encoder", "auto") == "software" and duration >= 60 and
                int((video or {}).get("width", 0)) >= 1920 and width >= 1920 and
                (video or {}).get("pix_fmt") in ("yuv420p", "nv12") and 0 < source_fps <= 30 and
                abs(request.get("fps", source_fps) - source_fps) < 0.01 and request.get("decode", "software") == "software" and
                request.get("filter_backend", "software") == "software" and request.get("deinterlace", "off") == "off" and
                request.get("hdr_policy", "reject") != "tone_map" and
                caps.get("system") == "Darwin" and caps.get("machine") == "arm64")
    if eligible:
        from .darwin import cpu_brand
        try:
            model = cpu_brand()
        except (OSError, ValueError, AttributeError):
            model = "unknown"
        if model == "Apple M4 Max":
            encoder, decoder, filters, validation = 4, 2, 2, 4
            resized = width * height < int(video["width"]) * int(video["height"])
            filters = 4 if resized else 2
            profile = "m4_max_long_software_resize" if resized else "m4_max_long_software"
            rotation = next((s.get("rotation", 0) for s in video.get("side_data_list", []) if "rotation" in s),
                            video.get("tags", {}).get("rotate", 0))
            hd = (not resized and width == int(video["width"]) == 1920 and height == int(video["height"]) and
                  0 < height <= 1080 and video.get("codec_name") in ("h264", "vp8") and
                  video.get("field_order") == "progressive" and rational(video.get("sample_aspect_ratio", "1:1"), 1) == 1 and
                  video.get("color_transfer") not in ("smpte2084", "arib-std-b67") and float(rotation) % 360 == 0 and
                  rational(video.get("r_frame_rate")) == source_fps and request.get("fps") == source_fps and
                  request.get("rate_control", "quality") == "quality" and "video_bitrate" not in request and
                  "checkpoint_seconds" not in request and
                  not any(name in request for name in ("decoder_threads", "filter_threads", "validation_threads")))
            if hd:
                encoder, validation = 8, 8
                profile = "m4_max_hd_software"
    decoder = request.get("decoder_threads", decoder)
    filters = request.get("filter_threads", filters)
    validation = request.get("validation_threads", validation)
    if encoder + decoder + filters + 1 > 14:
        raise FFV2Error("thread_budget_exceeded", "Codec/filter/audio thread budget সর্বোচ্চ 14।")
    return {"encoder_threads": encoder, "decoder_threads": decoder, "filter_threads": filters,
            "validation_threads": validation, "profile": profile,
            "policy_revision": "phase8-calibration-1", "encode_thread_budget": encoder + decoder + filters + 1}
