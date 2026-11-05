"""Bounded audio-only mixer: relative gain/offset, resampling ও peak limit।"""
from __future__ import annotations

from .advanced import COMMON, base, fields, finish
from .errors import FFV2Error
from .media import INPUT_LIMITS, probe, rational


def build_mix(request, settings, caps, *, restricted, allow_existing):
    fields(request, COMMON | {"start", "duration", "audio_rate", "audio_channels", "tracks", "primary_gain_db", "mix_normalize", "mix_limit"}, ("tracks",))
    missing = {"amix", "alimiter", "adelay", "apad", "atrim", "aresample", "aformat", "volume"} - set(caps["filters"])
    if missing:
        raise FFV2Error("filter_missing", "Audio mixing filter build-এ নেই।", details={"filters": sorted(missing)})
    rate, channels = request.get("audio_rate", 48000), request.get("audio_channels", 2)
    plan = base({**request, "audio_rate": rate, "audio_channels": channels}, settings, caps, "audio",
                restricted=restricted, allow_existing=allow_existing)
    media = [plan["source"]]
    normalized = []
    for track in request["tracks"]:
        source = probe(track["input"], settings, caps, restricted=restricted)
        if not source["audio"]:
            raise FFV2Error("audio_missing", "প্রতিটি mix track-এ audio stream প্রয়োজন।")
        if track.get("loop") and source["video"]:
            raise FFV2Error("mix_loop_video_unsupported", "Loop-এর জন্য audio-only source ব্যবহার করুন; আগে audio extract করা যায়।")
        if track.get("offset", 0) >= plan["expected"]["duration_seconds"]:
            raise FFV2Error("mix_track_outside_range", "Mix track offset output range-এর বাইরে।")
        media.append(source)
        normalized.append({**track, "input": source["path"]})
    decoder = request.get("decoder_threads", request.get("threads", 1))
    filters = request.get("filter_threads", 2)
    budget = len(media) * decoder + filters + 1
    if budget > 14:
        raise FFV2Error("thread_budget_exceeded", "একাধিক audio input-এর মোট thread budget সর্বোচ্চ 14।")
    duration = plan["expected"]["duration_seconds"]
    samples = round(duration * rate)
    argv = [caps["ffmpeg"], "-nostdin", "-hide_banner", "-v", "error", "-n", "-xerror", "-nostats", "-progress", "pipe:1",
            "-filter_threads", str(filters), "-filter_complex_threads", str(filters)]
    if caps.get("native_jsonl_progress"):
        argv += ["-progress_format", "jsonl"]
    all_tracks = [{"offset": 0, "gain_db": request.get("primary_gain_db", 0), "loop": False}, *normalized]
    graph = []
    layout = "mono" if channels == 1 else "stereo"
    for index, (source, track) in enumerate(zip(media, all_tracks)):
        argv += [*INPUT_LIMITS, "-threads", str(decoder)]
        if track.get("loop"):
            argv += ["-stream_loop", "-1"]
        start = request.get("start", 0) if index == 0 else 0
        argv += ["-ss", format(start, ".12g"), "-err_detect", "explode", "-i", source["path"]]
        audio_start = rational(source["audio"].get("start_time")) - rational(source["format"].get("start_time"))
        delay = round((track.get("offset", 0) + max(0, audio_start - start)) * rate)
        chain = (f"[{index}:{source['audio']['index']}]aresample={rate},aformat=sample_fmts=fltp:sample_rates={rate}:channel_layouts={layout},"
                 f"asetpts=PTS-STARTPTS,volume={track.get('gain_db', 0):.9g}dB")
        if delay:
            chain += f",adelay={delay}S:all=1"
        chain += f",apad=whole_len={samples},atrim=end_sample={samples}[a{index}]"
        graph.append(chain)
    graph.append("".join(f"[a{i}]" for i in range(len(media))) +
                 f"amix=inputs={len(media)}:duration=first:dropout_transition=0:normalize={int(request.get('mix_normalize', True))},"
                 f"alimiter=limit={request.get('mix_limit', 0.95):.9g}:level=0:latency=1,atrim=end_sample={samples}[mixed]")
    output_budget = samples * channels * 2 + 1024**2
    if output_budget > 64 * 1024**3:
        raise FFV2Error("output_budget_exceeded", "Audio mix output 64 GiB budget-এর বাইরে।")
    argv += ["-filter_complex", ";".join(graph), "-map", "[mixed]", "-vn", "-sn", "-dn", "-c:a", "pcm_s16le", "-ar", str(rate), "-ac", str(channels),
             "-threads:a", "1", "-map_metadata", "-1", "-f", "wav", "-rf64", "auto", "-fs", str(output_budget), "<STAGING_OUTPUT>"]
    plan.update(argv=argv, sources=media, runtime_tuning={"encoder_threads": 1, "decoder_threads": decoder, "filter_threads": filters,
                "validation_threads": request.get("validation_threads", 2), "encode_thread_budget": budget, "profile": "bounded_audio_mix"})
    plan["estimates"].update(job_memory_bytes=int((0.35 + 0.075 * len(media)) * 1024**3), output_budget_bytes=output_budget)
    plan["expected"].update(duration_seconds=samples / rate, audio_samples=samples, mix_peak_limit=request.get("mix_limit", 0.95))
    plan["warnings"].append("Audio-only mix; relative gain/offset, optional whole-file audio loop, normalization ও latency-compensated limiter apply হয়।")
    return finish(plan, request, settings, {"tracks": normalized})
