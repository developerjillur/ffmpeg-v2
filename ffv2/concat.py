"""Compatible packet copy অথবা bounded decoded concat normalization।"""
from __future__ import annotations

import math

from .advanced import COMMON, VIDEO, base, fields, finish
from .errors import FFV2Error
from .media import INPUT_LIMITS, probe, rational
from .video_policy import video_policy


def signature(media):
    keys = ("codec_type", "codec_name", "width", "height", "pix_fmt", "sample_aspect_ratio", "sample_rate", "channels",
            "channel_layout", "time_base", "extradata_hash", "color_range", "color_space", "color_transfer", "color_primaries")
    return [tuple(stream.get(key) for key in keys) for stream in media["streams"]]


def remove_options(argv, names):
    result, index = [], 0
    while index < len(argv):
        if argv[index] in names:
            index += 2
        else:
            result.append(argv[index])
            index += 1
    return result


def duration_of(source, video=False):
    stream = source["video"] if video else source["audio"]
    duration = rational((stream or {}).get("duration"))
    return duration if duration > 0 else source["duration_seconds"]


def build_concat(request, settings, caps, *, restricted, allow_existing):
    fields(request, COMMON | VIDEO | {"additional_inputs", "concat_mode", "audio_rate", "audio_channels"}, ("additional_inputs",))
    sources = [probe(path, settings, caps, restricted=restricted) for path in [request["input"], *request["additional_inputs"]]]
    mode = request.get("concat_mode", "normalize")
    if mode == "copy":
        if set(request) - ((COMMON - {"threads", "decoder_threads", "filter_threads"}) | {"additional_inputs", "concat_mode"}):
            raise FFV2Error("invalid_spec", "Copy concat-এ codec/filter/resize field প্রযোজ্য নয়।")
        reference = signature(sources[0])
        for source in sources:
            if signature(source) != reference:
                raise FFV2Error("concat_copy_incompatible", "Copy concat-এর codec configuration/time-base/geometry/colour এক হতে হবে; normalize mode ব্যবহার করুন।")
            if any(stream["codec_name"] in ("h264", "hevc", "aac") and not stream.get("extradata_hash") for stream in source["streams"]):
                raise FFV2Error("concat_configuration_unverified", "Copy concat-এর codec extradata identity নেই; normalize mode দিন।")
        from .planner import build_plan
        selected = {key: value for key, value in request.items() if key in COMMON - {"decoder_threads", "filter_threads"}}
        selected["operation"] = "remux"
        plan = build_plan(selected, settings, caps, restricted=restricted, allow_existing=allow_existing)
        duration = sum(source["duration_seconds"] for source in sources)
        budget = sum(source["fingerprint"]["size"] for source in sources) + 64 * 1024**2
        argv = [caps["ffmpeg"], "-nostdin", "-hide_banner", "-v", "error", "-n", "-xerror", "-nostats", "-progress", "pipe:1",
                "-max_alloc", "67108864", "-protocol_whitelist", "file", "-format_whitelist", INPUT_LIMITS[-1] + ",concat",
                "-f", "concat", "-safe", "0", "-auto_convert", "0", "-i", "<CONCAT_MANIFEST>", "-map", "0", "-c", "copy",
                "-map_metadata", "-1", "-f", "matroska", "-fs", str(budget), "<STAGING_OUTPUT>"]
        plan.update(argv=argv, sources=sources, preparation={"kind": "concat"})
        plan["expected"]["duration_seconds"] = duration
        plan["estimates"]["output_budget_bytes"] = budget
        plan["warnings"].append("Copy concat file-duration timestamps ব্যবহার করে; trim/normalization নয়। Payload conversion disabled; full decode যাচাই হবে।")
    else:
        if len(sources) > 8:
            raise FFV2Error("concat_input_budget", "Decoded concat সর্বোচ্চ 8টি input একবারে নেয়।")
        if any(not source["video"] for source in sources) and any(source["video"] for source in sources):
            raise FFV2Error("concat_media_mismatch", "Video/audio-only mixed concat-এর জন্য আগে একই media contract তৈরি করুন।")
        if all(not source["video"] for source in sources):
            plan = audio_concat(request, sources, settings, caps, restricted=restricted, allow_existing=allow_existing)
        else:
            plan = video_concat(request, sources, settings, caps, restricted=restricted, allow_existing=allow_existing)
    if plan["expected"]["duration_seconds"] > 86400 or plan["estimates"]["output_budget_bytes"] > 64 * 1024**3:
        raise FFV2Error("concat_budget_exceeded", "Joined duration/output budget 24 hours/64 GiB-এর বাইরে।")
    if "timeout_seconds" not in request:
        plan["timeout_seconds"] = max(120, min(43200, math.ceil(plan["expected"]["duration_seconds"] * 5 + 60)))
    return finish(plan, request, settings, {"additional_inputs": [source["path"] for source in sources[1:]]})


def input_arguments(caps, sources, decoder, filters):
    argv = [caps["ffmpeg"], "-nostdin", "-hide_banner", "-v", "error", "-n", "-xerror", "-nostats", "-progress", "pipe:1",
            "-filter_threads", str(filters), "-filter_complex_threads", str(filters), "-filter_buffered_frames", "64"]
    if caps.get("native_jsonl_progress"):
        argv += ["-progress_format", "jsonl"]
    for source in sources:
        argv += [*INPUT_LIMITS, "-threads", str(decoder), "-err_detect", "explode", "-i", source["path"]]
    return argv


def audio_concat(request, sources, settings, caps, *, restricted, allow_existing):
    if set(request) & VIDEO:
        raise FFV2Error("invalid_spec", "Audio-only concat-এ video field প্রযোজ্য নয়।")
    if any(not source["audio"] for source in sources):
        raise FFV2Error("audio_missing", "প্রতিটি audio concat input-এ audio stream প্রয়োজন।")
    rate, channels = request.get("audio_rate", 48000), request.get("audio_channels", 2)
    plan = base({**request, "audio_rate": rate, "audio_channels": channels}, settings, caps, "audio",
                restricted=restricted, allow_existing=allow_existing)
    decoder, filters = request.get("decoder_threads", 1), request.get("filter_threads", 2)
    if len(sources) * decoder + filters + 1 > 14:
        raise FFV2Error("thread_budget_exceeded", "Audio concat-এর total thread budget 14-এর বাইরে।")
    argv = input_arguments(caps, sources, decoder, filters)
    layout = "mono" if channels == 1 else "stereo"
    graph = [f"[{i}:{source['audio']['index']}]aresample={rate},aformat=sample_fmts=fltp:channel_layouts={layout},asetpts=PTS-STARTPTS[a{i}]"
             for i, source in enumerate(sources)]
    graph.append("".join(f"[a{i}]" for i in range(len(sources))) + f"concat=n={len(sources)}:v=0:a=1[joined]")
    duration = sum(duration_of(source) for source in sources)
    budget = math.ceil(duration * rate * channels * 2) + 1024**2
    argv += ["-filter_complex", ";".join(graph), "-map", "[joined]", "-vn", "-c:a", "pcm_s16le", "-ar", str(rate), "-ac", str(channels),
             "-threads:a", "1", "-map_metadata", "-1", "-f", "wav", "-rf64", "auto", "-fs", str(budget), "<STAGING_OUTPUT>"]
    plan.update(argv=argv, sources=sources)
    plan["expected"]["duration_seconds"] = duration
    plan["estimates"].update(job_memory_bytes=int((0.35 + len(sources) * 0.075) * 1024**3), output_budget_bytes=budget)
    plan["warnings"].append("Audio-only normalization decode/resample করে join করে; lossy codec padding actual decoder অনুযায়ী বাদ যায়।")
    return plan


def video_concat(request, sources, settings, caps, *, restricted, allow_existing):
    if request.get("decode", "software") != "software" or request.get("filter_backend", "software") != "software":
        raise FFV2Error("concat_hardware_filter_unsupported", "Multi-input normalization software decode/filter ব্যবহার করে; encoder VideoToolbox হতে পারে।")
    required = {"concat", "scale", "pad", "fps", "tpad", "trim", "aresample", "aformat", "apad", "atrim", "anullsrc"}
    if required - set(caps["filters"]):
        raise FFV2Error("filter_missing", "Decoded concat-এর required filters build-এ নেই।", details={"filters": sorted(required - set(caps["filters"]))})
    base_request = dict(request)
    first = sources[0]["video"]
    if first.get("color_transfer") not in ("smpte2084", "arib-std-b67") and first.get("color_primaries") != "bt2020":
        base_request.pop("hdr_policy", None)
        base_request.pop("source_peak_nits", None)
    base_request["decoder_threads"] = request.get("decoder_threads", 1)
    base_request["fps"] = request.get("fps", 30)
    plan = base(base_request, settings, caps, "transcode", restricted=restricted, allow_existing=allow_existing)
    decoder, filters = request.get("decoder_threads", 1), request.get("filter_threads", 2)
    encoder_threads = request.get("threads", 2)
    budget_threads = len(sources) * decoder + filters + encoder_threads + 1
    if budget_threads > 14:
        raise FFV2Error("thread_budget_exceeded", "Multi-input decoder/filter/encoder total thread budget সর্বোচ্চ 14।")
    width, height = plan["expected"]["width"], plan["expected"]["height"]
    fps, rate, channels = request.get("fps", 30), request.get("audio_rate", 48000), request.get("audio_channels", 2)
    layout = "mono" if channels == 1 else "stereo"
    graph, durations, colours = [], [], []
    for index, source in enumerate(sources):
        video = source["video"]
        policy_request = {**request, "operation": "transcode"}
        hdr = video.get("color_transfer") in ("smpte2084", "arib-std-b67") or video.get("color_primaries") == "bt2020"
        if not hdr:
            policy_request.pop("hdr_policy", None)
            policy_request.pop("source_peak_nits", None)
        before, colour_filters, _, colour_expected, warnings = video_policy(policy_request, video, caps)
        colours.append(tuple(colour_expected.get(key, video.get(key)) for key in ("color_primaries", "color_transfer", "color_space", "color_range")))
        frames = max(1, round(duration_of(source, video=True) * fps))
        duration = frames / fps
        durations.append(duration)
        chain = before + colour_filters + [f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1",
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black", "setsar=1", "settb=AVTB", "setpts=PTS-STARTPTS",
                    f"fps={fps}", f"tpad=stop_mode=clone:stop_duration={1/fps:.12g}", f"trim=end_frame={frames}", f"setpts=N/({fps}*TB)", "format=yuv420p"]
        graph.append(f"[{index}:{video['index']}]" + ",".join(chain) + f"[v{index}]")
        samples = round(duration * rate)
        if source["audio"]:
            relative_start = rational(source["audio"].get("start_time")) - rational(video.get("start_time"))
            audio = f"[{index}:{source['audio']['index']}]aresample={rate},aformat=sample_fmts=fltp:channel_layouts={layout},asetpts=PTS-STARTPTS"
            if relative_start > 0:
                audio += f",adelay={round(relative_start*rate)}S:all=1"
            elif relative_start < 0:
                audio += f",atrim=start_sample={round(-relative_start*rate)},asetpts=PTS-STARTPTS"
            audio += f",apad=whole_len={samples},atrim=end_sample={samples}[a{index}]"
        else:
            audio = f"anullsrc=r={rate}:cl={layout},atrim=end_sample={samples},asetpts=PTS-STARTPTS[a{index}]"
        graph.append(audio)
        plan["warnings"] += warnings
    if len(set(colours)) != 1:
        raise FFV2Error("concat_colour_mismatch", "Joined inputs-এর colour policy এক নয়; আগে explicit conversion করে একই colour contract তৈরি করুন।")
    graph.append("".join(f"[v{i}][a{i}]" for i in range(len(sources))) + f"concat=n={len(sources)}:v=1:a=1[vjoined][ajoined]")
    input_end = plan["argv"].index("-i") + 2
    tail = remove_options(plan["argv"][input_end:], {"-map", "-vf", "-t", "-c:a", "-b:a", "-threads:a", "-fs"})
    duration = sum(durations)
    payload_budget = max(0, plan["estimates"]["output_budget_bytes"] - 64 * 1024**2)
    budget = math.ceil(payload_budget * duration / plan["expected"]["duration_seconds"]) + 64 * 1024**2
    argv = input_arguments(caps, sources, decoder, filters)
    argv += ["-filter_complex", ";".join(graph), "-map", "[vjoined]", "-map", "[ajoined]", "-t", format(duration, ".12g"),
             "-c:a", "aac", "-b:a", "160k", "-ar", str(rate), "-ac", str(channels), "-threads:a", "1", *tail,
             "-fs", str(budget), "<STAGING_OUTPUT>"]
    # Base tail-এর placeholder সরিয়ে নতুন একমাত্র output বসে।
    argv = [item for index, item in enumerate(argv) if item != "<STAGING_OUTPUT>" or index == len(argv) - 1]
    plan.update(argv=argv, sources=sources, concat_timing={"clip_durations": durations, "fps": fps, "audio_rate": rate})
    plan["expected"].update(duration_seconds=duration, fps=fps, video_frames=sum(round(d * fps) for d in durations),
                            audio_codec="aac", audio_streams=1, audio_rate=rate, audio_channels=channels)
    plan["runtime_tuning"].update(decoder_threads=decoder, filter_threads=filters, encode_thread_budget=budget_threads, profile="bounded_concat")
    memory = plan["estimates"]["job_memory_bytes"] + sum(s["video"]["width"] * s["video"]["height"] * 6 * (decoder + 8) for s in sources[1:])
    plan["estimates"].update(job_memory_bytes=memory, output_budget_bytes=budget)
    plan["warnings"].append("Decoded concat integer CFR-এ clip durations quantize করে; geometry pad/scale, 48k/default stereo ও missing-audio silence explicit।")
    return plan
