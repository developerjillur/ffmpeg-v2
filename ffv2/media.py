from __future__ import annotations

import json
import math
from fractions import Fraction

from .errors import FFV2Error
from .io import capture, fingerprint, input_path
from .bindings import strong_identity

DEMUXERS = "mov,matroska,webm,avi,wav,aiff,mp3,flac,ogg,aac,mpegts,mpegvideo,ivf"
INPUT_LIMITS = ["-max_alloc", "67108864", "-probesize", "8388608", "-analyzeduration", "5000000",
                "-protocol_whitelist", "file", "-format_whitelist", DEMUXERS]


def rational(raw, default=0):
    try:
        value = float(Fraction(str(raw).replace(":", "/")))
        return value if math.isfinite(value) else default
    except (ValueError, ZeroDivisionError):
        return default


def probe_path(path, ffprobe, *, image=False):
    limits = list(INPUT_LIMITS)
    if image:
        limits[-1] += ",image2,jpeg_pipe,png_pipe,webp_pipe"
    before = fingerprint(path)
    strong_before = strong_identity(path)
    argv = [ffprobe, "-v", "error", *limits, *(["-f", "image2", "-pattern_type", "none"] if image else []), "-threads", "1", "-show_data_hash", "sha256", "-show_entries",
            "format=format_name,duration,size,start_time:stream=index,codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,r_frame_rate,sample_aspect_ratio,color_range,color_space,color_transfer,color_primaries,field_order,sample_rate,channels,channel_layout,sample_fmt,start_time,duration,duration_ts,time_base,nb_frames,extradata_hash:stream_tags=rotate:stream_side_data:stream_disposition=attached_pic",
            "-of", "json", str(path)]
    code, out, err = capture(argv)
    if code:
        raise FFV2Error("invalid_media", "এই file-এর media metadata পড়া যায়নি।",
                        details={"stderr": err[-4000:]})
    try:
        raw = json.loads(out)
        streams = raw.get("streams", [])
        if not isinstance(streams, list) or not 1 <= len(streams) <= 64:
            raise ValueError("stream count")
        duration = float(raw.get("format", {}).get("duration", 0))
        if not math.isfinite(duration) or not image and duration <= 0:
            raise ValueError("duration")
    except (ValueError, TypeError) as error:
        raise FFV2Error("invalid_media", "Media-এর নির্ভরযোগ্য positive duration নেই।") from error
    if fingerprint(path) != before or strong_identity(path) != strong_before:
        raise FFV2Error("source_changed", "Metadata পড়ার সময় input বদলেছে।")
    video = next((s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    return {"path": str(path), "fingerprint": before, "strong_identity": strong_before, "duration_seconds": duration,
            "format": raw.get("format", {}), "streams": streams, "video": video, "audio": audio}


def probe(raw_path, settings, caps, *, restricted=False):
    return probe_path(input_path(raw_path, settings, restricted=restricted), caps["ffprobe"])
