from __future__ import annotations

import math
import shlex
from pathlib import Path

from .config import GIB
from .errors import FFV2Error
from .io import digest, output_path
from .media import INPUT_LIMITS, probe, rational
from .video_policy import video_policy

SPEC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["operation", "input", "output"],
    "properties": {
        "operation": {"type": "string", "enum": ["transcode", "remux", "audio", "frame", "contact_sheet", "concat", "subtitle", "audio_mix", "image"]},
        "input": {"type": "string", "minLength": 1, "maxLength": 4096},
        "output": {"type": "string", "minLength": 1, "maxLength": 4096},
        "encoder": {"type": "string", "enum": ["auto", "software", "videotoolbox"]},
        "decode": {"type": "string", "enum": ["software", "videotoolbox"]},
        "filter_backend": {"type": "string", "enum": ["software", "videotoolbox"]},
        "priority": {"type": "integer", "minimum": -10, "maximum": 10},
        "deinterlace": {"type": "string", "enum": ["off", "bwdif"]},
        "hdr_policy": {"type": "string", "enum": ["reject", "tone_map"]},
        "source_peak_nits": {"type": "number", "minimum": 100, "maximum": 10000},
        "max_width": {"type": "integer", "minimum": 2, "maximum": 3840},
        "max_height": {"type": "integer", "minimum": 2, "maximum": 3840},
        "start": {"type": "number", "minimum": 0},
        "duration": {"type": "number", "exclusiveMinimum": 0, "maximum": 86400},
        "fps": {"type": "integer", "minimum": 1, "maximum": 60},
        "video_bitrate": {"type": "integer", "minimum": 100000, "maximum": 80000000},
        "rate_control": {"type": "string", "enum": ["quality", "bitrate"]},
        "audio_rate": {"type": "integer", "enum": [16000, 24000, 44100, 48000]},
        "audio_channels": {"type": "integer", "enum": [1, 2]},
        "count": {"type": "integer", "minimum": 2, "maximum": 64},
        "columns": {"type": "integer", "minimum": 1, "maximum": 8},
        "sampling": {"type": "string", "enum": ["auto", "single_pass", "seek"]},
        "threads": {"type": "integer", "minimum": 1, "maximum": 8},
        "decoder_threads": {"type": "integer", "minimum": 1, "maximum": 4},
        "filter_threads": {"type": "integer", "minimum": 1, "maximum": 4},
        "validation_threads": {"type": "integer", "minimum": 1, "maximum": 8},
        "checkpoint_seconds": {"type": "integer", "minimum": 5, "maximum": 600},
        "additional_inputs": {"type": "array", "minItems": 1, "maxItems": 15,
                              "items": {"type": "string", "minLength": 1, "maxLength": 4096}},
        "concat_mode": {"type": "string", "enum": ["copy", "normalize"]},
        "subtitle_file": {"type": "string", "minLength": 1, "maxLength": 4096},
        "subtitle_offset": {"type": "number", "minimum": -86400, "maximum": 86400},
        "subtitle_font": {"type": "string", "enum": ["sans", "bengali", "custom"]},
        "font_file": {"type": "string", "minLength": 1, "maxLength": 4096},
        "font_family": {"type": "string", "minLength": 1, "maxLength": 64},
        "font_size": {"type": "number", "minimum": 8, "maximum": 256},
        "background": {"type": "string", "pattern": "#[0-9A-Fa-f]{6}", "minLength": 7, "maxLength": 7},
        "image_bit_depth": {"type": "integer", "enum": [8, 16]},
        "image_quality": {"type": "integer", "minimum": 2, "maximum": 31},
        "jpeg_chroma": {"type": "string", "enum": ["420", "444"]},
        "compression_level": {"type": "integer", "minimum": 0, "maximum": 9},
        "primary_gain_db": {"type": "number", "minimum": -60, "maximum": 12},
        "mix_normalize": {"type": "boolean"},
        "mix_limit": {"type": "number", "minimum": 0.0625, "maximum": 1},
        "tracks": {"type": "array", "minItems": 1, "maxItems": 7, "items": {
            "type": "object", "additionalProperties": False, "required": ["input"], "properties": {
                "input": {"type": "string", "minLength": 1, "maxLength": 4096},
                "offset": {"type": "number", "minimum": 0, "maximum": 86400},
                "gain_db": {"type": "number", "minimum": -60, "maximum": 12}, "loop": {"type": "boolean"}}}},
        "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": 43200},
    },
}


def validate_spec(value):
    from .schema import validate
    validate(value, SPEC_SCHEMA)
    if value.get('threads', 2) > 4 and (value['operation'] != 'transcode' or value.get('encoder') != 'software'):
        raise FFV2Error('invalid_spec', '4-এর বেশি encoder threads শুধু explicit software transcode-এ দিন; total pool budget বহাল।')
    return dict(value)


def dimensions(video, max_width, max_height, *, even=True):
    width, height = int(video["width"]), int(video["height"])
    sar = rational(video.get("sample_aspect_ratio", "1:1"), 1) or 1
    ratio = width * sar / height
    rotation = int(float(next((s["rotation"] for s in video.get("side_data_list", []) if "rotation" in s),
                              video.get("tags", {}).get("rotate", 0)))) % 360
    if rotation not in (0, 90, 180, 270):
        raise FFV2Error("unsupported_rotation", "এই rotation-এর জন্য আলাদা যাচাই প্রয়োজন।")
    if rotation in (90, 270):
        width, height, ratio = height, width, 1 / ratio
    # Display aspect ratio বজায় থাকে; input-এর displayed height-এর বেশি upscale হয় না।
    target_height = min(height, max_height, max_width / ratio)
    target_width = target_height * ratio
    quantum = 2 if even else 1
    return (max(2, math.floor(target_width / quantum + 1e-9) * quantum),
            max(2, math.floor(target_height / quantum + 1e-9) * quantum))


def build_plan(value, settings, caps, *, restricted=False, allow_existing=False):
    request = validate_spec(value)
    if request["operation"] in ("concat", "subtitle", "audio_mix", "image"):
        from .advanced import build
        return build(request, settings, caps, restricted=restricted, allow_existing=allow_existing)
    media = probe(request["input"], settings, caps, restricted=restricted)
    source = Path(media["path"])
    output = output_path(request["output"], source, settings, allow_existing=allow_existing)
    operation = request["operation"]
    allowed = {"operation", "input", "output", "threads", "timeout_seconds", "priority", "validation_threads"}
    if operation != "remux":
        allowed |= {"start", "duration"} if operation != "frame" else {"start"}
    if operation in ("transcode", "frame", "contact_sheet"):
        allowed |= {"max_width", "max_height", "decode", "deinterlace", "hdr_policy", "source_peak_nits", "decoder_threads", "filter_threads"}
    if operation in ("frame", "contact_sheet"):
        allowed |= {"image_bit_depth", "image_quality", "compression_level", "jpeg_chroma"}
    if operation == "contact_sheet":
        allowed |= {"count", "columns", "sampling"}
    if operation == "transcode":
        allowed |= {"encoder", "fps", "video_bitrate", "rate_control", "filter_backend", "checkpoint_seconds"}
    if operation == "audio":
        allowed |= {"audio_rate", "audio_channels"}
    if set(request) - allowed:
        raise FFV2Error("invalid_spec", "এই operation-এ field-টি প্রযোজ্য নয়।", details={"fields": sorted(set(request) - allowed)})
    suffixes = {"transcode": (".mp4",), "remux": (".mkv",), "audio": (".wav",),
                "frame": (".jpg", ".jpeg", ".png"), "contact_sheet": (".jpg", ".jpeg", ".png")}
    if output.suffix.lower() not in suffixes[operation]:
        raise FFV2Error("invalid_container", "Operation-এর জন্য output extension ঠিক করুন।", details={"allowed": suffixes[operation]})
    start = float(request.get("start", 0))
    duration = float(request.get("duration", media["duration_seconds"] - start))
    if start >= media["duration_seconds"] or duration <= 0 or start + duration > media["duration_seconds"] + 0.001:
        raise FFV2Error("invalid_time_range", "সময়-সীমা input duration-এর মধ্যে হতে হবে।")
    if operation != "frame" and duration > 86400:
        raise FFV2Error("duration_budget_exceeded", "প্রথম release-এ প্রতি job সর্বোচ্চ 24 ঘণ্টার range; ছোট range বাছুন।")
    video, audio = media["video"], media["audio"]
    if operation in ("transcode", "frame", "contact_sheet") and not video:
        raise FFV2Error("video_missing", "এই operation-এর জন্য video stream প্রয়োজন।")
    if operation == "audio" and not audio:
        raise FFV2Error("audio_missing", "Input-এ audio stream নেই।")
    warnings = []
    before_selection, before_scale, video_options, policy_expected = [], [], [], {}
    fps = rational((video or {}).get("avg_frame_rate")) or rational((video or {}).get("r_frame_rate")) or 30
    if operation in ("transcode", "frame", "contact_sheet"):
        if not all(type(video.get(k)) is int and 2 <= video[k] <= 8192 for k in ("width", "height")):
            raise FFV2Error("invalid_dimensions", "Source-এর positive supported dimensions পাওয়া যায়নি।")
        before_selection, before_scale, video_options, policy_expected, policy_warnings = video_policy(request, video, caps)
        warnings += policy_warnings
        if int(video["width"]) * int(video["height"]) > 8192 * 4320 or fps > 120:
            raise FFV2Error("source_budget_exceeded", "এই source প্রথম release-এর resolution/frame-rate budget-এর বাইরে।")
        width, height = dimensions(video, request.get("max_width", 320 if operation == "contact_sheet" else 1920),
                                   request.get("max_height", 180 if operation == "contact_sheet" else 1080))
        if width * height > 3840 * 2160:
            raise FFV2Error("output_resolution_budget", "প্রথম release-এ সর্বোচ্চ 3840×2160 pixel budget।")
        if any(bit in video.get("pix_fmt", "") for bit in ("10", "12", "14", "16")) and output.suffix.lower() != ".png":
            warnings.append("এই operation 8-bit output তৈরি করে; source bit depth অক্ষুণ্ণ থাকে না।")
    else:
        width, height = 0, 0
    from .tuning import pools
    tuning = pools(request, video, duration, caps, width=width, height=height)
    threads = tuning["encoder_threads"]
    timeout = request.get("timeout_seconds", 120 if operation == "frame" else max(120, min(43200, math.ceil(duration * 5 + 60))))
    expected = {"duration_seconds": duration, "video_codec": None, "audio_codec": None, **policy_expected}
    decode_filters = []
    argv = [caps["ffmpeg"], "-nostdin", "-hide_banner", "-loglevel", "info" if operation in ("frame", "contact_sheet") else "error",
            "-n", "-xerror", "-nostats", "-progress", "pipe:1", "-stats_period", "1",
            "-filter_threads", str(tuning["filter_threads"]), "-filter_complex_threads", str(tuning["filter_threads"]),
            *INPUT_LIMITS, "-threads", str(tuning["decoder_threads"])]
    if caps.get("native_jsonl_progress"):
        argv += ["-progress_format", "jsonl"]
    if operation != "remux":
        if request.get("decode", "software") == "videotoolbox":
            if caps["system"] != "Darwin":
                raise FFV2Error("hardware_unavailable", "VideoToolbox macOS-এর জন্য।")
            surfaces = {"yuv420p":"nv12", "yuvj420p":"nv12", "nv12":"nv12", "yuv420p10le":"p010le", "p010le":"p010le"}
            surface = surfaces.get(video.get("pix_fmt"))
            if not surface or "hwdownload" not in caps["filters"]:
                raise FFV2Error("hardware_surface_unsupported", "এই source-এর explicit VideoToolbox surface policy যাচাই করা হয়নি; software decode ব্যবহার করুন।")
            argv += ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
            decode_filters = ["hwdownload", "format=" + surface]
            expected["hardware_decode_required"] = True
            warnings.append("VideoToolbox hardware frame ও hwdownload বাধ্যতামূলক; CPU decode নীরবে hardware success হবে না।")
        if operation in ("frame", "contact_sheet"):
            argv += ["-copyts"]
        argv += ["-ss", format(start, ".9g")]
    argv += ["-err_detect", "explode", "-i", str(source)]
    encoder = None
    if operation == "transcode":
        choice = request.get("encoder", "auto")
        quality_requested = request.get("rate_control") == "quality"
        if choice == "videotoolbox" and quality_requested:
            raise FFV2Error("rate_control_unsupported", "এই hardware preset bitrate ব্যবহার করে; quality mode-এর জন্য software অথবা auto encoder দিন।")
        small_software = (choice == "auto" and caps["system"] == "Darwin" and caps.get("machine") == "arm64"
                          and width * height <= 640 * 360 and duration <= 4 and fps <= 30 and "libx264" in caps["encoders"])
        use_hardware = choice == "videotoolbox" or (choice == "auto" and not small_software and not quality_requested and caps["system"] == "Darwin" and "h264_videotoolbox" in caps["encoders"])
        if small_software:
            warnings.append("ছোট ≤360p/4s/30fps clip-এ software বাছা হয়েছে: স্থানীয় M4 fixture-এ hardware startup ধীর ছিল। Explicit encoder দিয়ে override করা যায়।")
        encoder = "h264_videotoolbox" if use_hardware else "libx264"
        if encoder not in caps["encoders"]:
            raise FFV2Error("encoder_missing", "নির্বাচিত encoder এই FFmpeg build-এ নেই।", details={"encoder": encoder})
        bitrate = request.get("video_bitrate", max(1_000_000, min(50_000_000, math.ceil(width * height * min(request.get("fps", fps), 60) * 0.10))))
        rate_control = request.get("rate_control", "bitrate" if use_hardware or "video_bitrate" in request else "quality")
        if not use_hardware and rate_control == "quality" and "video_bitrate" in request:
            raise FFV2Error("rate_control_conflict", "Software quality mode-এ explicit bitrate প্রযোজ্য নয়; rate_control=bitrate দিন।")
        argv += ["-map", f"0:{video['index']}"]
        if audio:
            argv += ["-map", f"0:{audio['index']}"]
        hardware_filter = request.get("filter_backend", "software") == "videotoolbox"
        if hardware_filter:
            rotation = next((s.get("rotation", 0) for s in video.get("side_data_list", []) if "rotation" in s),
                            video.get("tags", {}).get("rotate", 0))
            if (request.get("decode") != "videotoolbox" or not use_hardware or
                    video.get("pix_fmt") not in ("yuv420p", "nv12") or
                    video.get("color_range") == "pc" or before_selection or before_scale or
                    rational(video.get("sample_aspect_ratio", "1:1"), 1) != 1 or float(rotation) % 360 or
                    video.get("field_order") not in ("progressive", "unknown", None)):
                raise FFV2Error("hardware_filter_unsupported", "Hardware scaling-এর জন্য 8-bit 4:2:0 SDR, square pixels, unrotated progressive source ও VideoToolbox decode/encode প্রয়োজন।")
            if "scale_vt" not in caps["filters"]:
                raise FFV2Error("filter_missing", "এই build-এ scale_vt নেই।")
            filters = f"scale_vt=w={width}:h={height},setsar=1"
            expected["hardware_filter_required"] = True
            warnings = [w for w in warnings if "hwdownload বাধ্যতামূলক" not in w]
            warnings.append("Hardware-frame scaling-এ explicit CPU download/scale নেই; scaler interpolation software থেকে ভিন্ন হতে পারে।")
        else:
            filters = ",".join(decode_filters + before_selection + before_scale + [f"scale={width}:{height}", "setsar=1"])
        argv += ["-t", format(duration, ".9g"), "-vf", filters, "-c:v", encoder,
                 "-threads:v", str(threads), "-pix_fmt", "videotoolbox_vld" if hardware_filter else "yuv420p"]
        argv += video_options
        if "fps" in request:
            argv += ["-r", str(request["fps"]), "-fps_mode", "cfr"]
        else:
            argv += ["-fps_mode", "vfr"]
        if use_hardware:
            argv += ["-allow_sw", "0", "-realtime", "0", "-b:v", str(bitrate)]
            warnings.append("VideoToolbox session runtime-এ যাচাই হবে; hardware ব্যর্থ হলে নীরব software fallback হবে না।")
        else:
            argv += ["-preset", "veryfast"]
            argv += ["-b:v", str(bitrate)] if rate_control == "bitrate" else ["-crf", "20"]
        if audio:
            argv += ["-c:a", "aac", "-b:a", "160k", "-threads:a", "1"]
        argv += ["-map_metadata", "-1", "-map_chapters", "-1", "-movflags", "+faststart", "-f", "mp4"]
        expected.update(video_codec="h264", audio_codec="aac" if audio else None,
                        width=width, height=height, fps=request.get("fps"), video_streams=1, audio_streams=int(bool(audio)))
        # CRF-এর bitrate আগাম নির্ভুল জানা যায় না; বড় reserve, watchdog ও duration validation প্রয়োজন।
        budget = math.ceil(duration * ((bitrate * (3 if not use_hardware and rate_control != "bitrate" else 1.6)) + 160000) / 8) + 64 * 1024 ** 2
        warnings.append("প্রথম video ও audio stream ব্যবহৃত হয়; অন্যান্য stream, subtitle, metadata ও chapter এই preset-এ অন্তর্ভুক্ত নয়।")
    elif operation == "remux":
        argv += ["-map", "0", "-c", "copy", "-f", "matroska"]
        expected["stream_codecs"] = sorted((s["codec_type"], s["codec_name"]) for s in media["streams"])
        budget = math.ceil(media["fingerprint"]["size"] * 1.25) + 64 * 1024 ** 2
        warnings.append("Stream copy পুনরায় encode করে না; সব source stream Matroska-তে mux করা সম্ভব নাও হতে পারে।")
    elif operation == "audio":
        rate, channels = request.get("audio_rate", 16000), request.get("audio_channels", 1)
        argv += ["-map", f"0:{audio['index']}", "-vn", "-sn", "-dn", "-t", format(duration, ".9g"),
                 "-c:a", "pcm_s16le", "-ar", str(rate), "-ac", str(channels), "-threads:a", "1", "-map_metadata", "-1", "-f", "wav", "-rf64", "auto"]
        expected.update(audio_codec="pcm_s16le", audio_rate=rate, audio_channels=channels, video_streams=0, audio_streams=1)
        budget = math.ceil(duration * rate * channels * 2) + 1024 ** 2
    else:
        filters = ",".join(before_scale + [f"scale={width}:{height}", "setsar=1", "showinfo@ffv2_samples"])
        seek_sampling = False
        if operation == "contact_sheet":
            count, columns = request.get("count", 16), request.get("columns", 4)
            columns = min(columns, count)
            rows = math.ceil(count / columns)
            source_start = rational(video.get("start_time", "0"))
            interval = duration / count
            if interval < 1 / fps:
                raise FFV2Error("sample_density_exceeded", "এই range-এ frame count কমান অথবা duration বাড়ান।")
            sampling = request.get("sampling", "auto")
            seek_allowed = count <= 8 and not before_selection and int(video["width"]) * int(video["height"]) * 60 * count <= 8 * GIB
            if sampling == "seek" and not seek_allowed:
                raise FFV2Error("seek_sampling_unsupported", "Seek sampling সর্বোচ্চ 8টি progressive frame-এর জন্য; অন্য ক্ষেত্রে single_pass দিন।")
            seek_sampling = sampling == "seek" or sampling == "auto" and seek_allowed and interval >= 30
            if seek_sampling and tuning["decoder_threads"] + count - 1 + tuning["filter_threads"] + 1 > 14:
                raise FFV2Error("thread_budget_exceeded", "Sparse decoder/filter/encoder thread budget সর্বোচ্চ 14।")
            filters = (f"select='lt(selected_n,{count})*gte(t,{start + source_start:.12g}+selected_n*{interval:.12g})',"
                       + filters + f",tile={columns}x{rows}:nb_frames={count}")
            expected.update(sample_count=count, columns=columns, rows=rows, cell_width=width, cell_height=height,
                            sample_interval_seconds=interval, requested_seconds=start,
                            source_video_start=source_start, sampling_method="seek" if seek_sampling else "single_pass")
            if seek_sampling:
                graph = []
                for index in range(count):
                    if index:
                        argv += [*INPUT_LIMITS, "-threads", "1"]
                        if request.get("decode") == "videotoolbox":
                            argv += ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
                        argv += ["-ss", format(start + index * interval, ".12g"), "-err_detect", "explode", "-i", str(source)]
                    download = ",".join(decode_filters) + "," if decode_filters else ""
                    graph.append(f"[{index}:{video['index']}]" + download + f"trim=end_frame=1,scale={width}:{height},setsar=1,"
                                 f"showinfo@ffv2_sample_{index},setpts=PTS-STARTPTS[s{index}]")
                layout = "|".join(f"{i % columns * width}_{i // columns * height}" for i in range(count))
                graph.append("".join(f"[s{i}]" for i in range(count)) + f"xstack=inputs={count}:layout={layout}:fill=black[sheet]")
                complex_filter = ";".join(graph)
            width, height = width * columns, height * rows
            if width > 8192 or height > 8192 or width * height > 32 * 1024 ** 2:
                raise FFV2Error("sheet_size_exceeded", "Contact sheet-এর cell size অথবা count কমান।")
            warnings.append("প্রতি target-এর প্রথম উপলব্ধ decoded frame নেওয়া হয়; receipt-এ actual source PTS থাকে।")
            warnings.append("Sparse seek সর্বোচ্চ 8টি bounded decoder ব্যবহার করে; প্রতিটি frame-এর actual PTS যাচাই হবে।" if seek_sampling else
                            "Single-pass sheet ঘন sampling-এর জন্য; sparse range ও count≤8 হলে auto seek ব্যবহার করতে পারে।")
        filters = ",".join(decode_filters + before_selection + [filters])
        argv += (["-filter_complex", complex_filter, "-map", "[sheet]"] if seek_sampling else
                 ["-map", f"0:{video['index']}", "-vf", filters])
        from .images import image_format, image_encoder
        image_policy = image_format(request, video)
        argv += ["-an", "-sn", "-dn", "-frames:v", "1", *image_encoder(request, image_policy), *video_options,
                 "-fps_mode", "passthrough", "-f", "image2", "-update", "1"]
        expected.update(video_codec=image_policy["codec"], width=width, height=height, requested_seconds=start,
                        source_video_start=rational(video.get("start_time", "0")), video_streams=1, audio_streams=0)
        budget = 64 * 1024 ** 2 if operation == "contact_sheet" else 16 * 1024 ** 2
        if image_policy["png"]:
            budget = max(budget, width * height * (4 if image_policy["alpha"] else 3) * (image_policy["depth"] // 8) + 4 * 1024**2)
    if budget > 64 * GIB:
        raise FFV2Error("output_budget_exceeded", "এক job-এর estimated output budget 64 GiB-এর বেশি; ছোট range-এ ভাগ করুন।")
    argv += ["-fs", str(budget), "<STAGING_OUTPUT>"]
    if video and operation in ("transcode", "frame", "contact_sheet"):
        memory = int(0.5 * GIB + int(video["width"]) * int(video["height"]) * 6 * (tuning["decoder_threads"] + 8) +
                     width * height * 6 * (threads + 8))
        if request.get("hdr_policy") == "tone_map":
            memory += int(video["width"]) * int(video["height"]) * 48
        if operation == "contact_sheet" and seek_sampling:
            memory += int(video["width"]) * int(video["height"]) * 6 * 10 * (count - 1)
    else:
        memory = int(0.35 * GIB)
    normalized = {**request, "input": str(source), "output": str(output)}
    plan = {"schema_version": 1, "spec": normalized, "source": media, "runtime_tuning": tuning,
            "binary": {k: caps[k] for k in ("ffmpeg", "ffprobe", "ffmpeg_version", "ffprobe_version", "ffmpeg_identity", "ffprobe_identity")},
            "encoder": encoder, "hardware_runtime_verified": False if encoder == "h264_videotoolbox" else None,
            "expected": expected, "estimates": {"job_memory_bytes": memory, "output_budget_bytes": budget,
                                                 "method": "conservative heuristic; not measured peak"},
            "timeout_seconds": timeout, "argv": argv, "warnings": warnings}
    if caps.get("engine_selection_id"):
        plan["binary"]["engine_selection_id"] = caps["engine_selection_id"]
    if caps.get("runtime_binding"):
        plan["binary"]["runtime_binding"] = caps["runtime_binding"]
    from .bindings import strong_identity
    if plan["source"].get("strong_identity", strong_identity(source)) != strong_identity(source):
        raise FFV2Error("source_changed", "Planning-এর সময় source বদলেছে।")
    plan["source"]["strong_identity"] = strong_identity(source)
    if "checkpoint_seconds" in request:
        from .checkpoints import configure
        configure(plan)
    from .bindings import workflow_identity
    plan['runtime_code_id'] = workflow_identity()
    plan["plan_id"] = digest(plan)
    plan["display_command"] = shlex.join(argv)
    return plan
