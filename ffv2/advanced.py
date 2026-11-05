"""একাধিক source, subtitle ও image workflow-এর shared preparation contract।"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shlex
import shutil

from .bindings import assert_sources, strong_identity
from .errors import FFV2Error
from .io import digest, fingerprint, input_path, output_path
from . import subtitles

COMMON = {"operation", "input", "output", "threads", "priority", "decoder_threads", "filter_threads", "validation_threads", "timeout_seconds"}
VIDEO = {"encoder", "decode", "filter_backend", "max_width", "max_height", "fps", "video_bitrate", "rate_control",
         "deinterlace", "hdr_policy", "source_peak_nits"}


def fields(request, allowed, required=()):
    if set(request) - set(allowed) or set(required) - set(request):
        raise FFV2Error("invalid_spec", "এই operation-এর required/allowed field ঠিক করুন।",
                        details={"unknown": sorted(set(request) - set(allowed)), "missing": sorted(set(required) - set(request))})


def asset(path, kind, maximum):
    path = Path(path)
    before = strong_identity(path)
    if not path.is_file() or not 0 < before["size"] <= maximum:
        raise FFV2Error("asset_size_exceeded", "Subtitle/font asset-এর size গ্রহণযোগ্য নয়।")
    raw = path.read_bytes()
    if strong_identity(path) != before:
        raise FFV2Error("source_changed", "Asset পড়ার সময়ে source বদলেছে।")
    return {"kind": kind, "path": str(path), "fingerprint": fingerprint(path), "strong_identity": before,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}, raw


def base(request, settings, caps, operation, *, restricted, allow_existing):
    from .planner import build_plan
    allowed = COMMON | {"start", "duration"} | (VIDEO if operation == "transcode" else {"audio_rate", "audio_channels"})
    value = {k: v for k, v in request.items() if k in allowed}
    value["operation"] = operation
    value["threads"] = request.get("threads", 2)
    if operation == "audio":
        value.pop("decoder_threads", None)
        value.pop("filter_threads", None)
    result = build_plan(value, settings, caps, restricted=restricted, allow_existing=allow_existing)
    if "threads" not in request:
        result["runtime_tuning"]["profile"] = "extended_conservative"
    return result


def finish(plan, request, settings, normalized=None):
    from .bindings import workflow_identity
    plan['runtime_code_id'] = workflow_identity()
    spec = {**request, "input": plan["source"]["path"], "output": plan["spec"]["output"], **(normalized or {})}
    for source in [plan["source"], *plan.get("sources", []), *plan.get("assets", [])]:
        output_path(spec["output"], Path(source["path"]), settings, allow_existing=True)
    plan["spec"] = spec
    plan.pop("plan_id", None)
    plan.pop("display_command", None)
    plan["plan_id"] = digest(plan)
    plan["display_command"] = shlex.join(plan["argv"])
    return plan


def build(request, settings, caps, *, restricted=False, allow_existing=False):
    operation = request["operation"]
    if operation == "subtitle":
        return build_subtitle(request, settings, caps, restricted=restricted, allow_existing=allow_existing)
    if operation == "audio_mix":
        from .mix import build_mix
        return build_mix(request, settings, caps, restricted=restricted, allow_existing=allow_existing)
    if operation == "concat":
        from .concat import build_concat
        return build_concat(request, settings, caps, restricted=restricted, allow_existing=allow_existing)
    from .images import build_image
    return build_image(request, settings, caps, restricted=restricted, allow_existing=allow_existing)


def build_subtitle(request, settings, caps, *, restricted, allow_existing):
    fields(request, COMMON | VIDEO | {"start", "duration", "subtitle_file", "subtitle_offset", "subtitle_font", "font_file", "font_family", "font_size"},
           ("subtitle_file",))
    if "ass" not in caps["filters"]:
        raise FFV2Error("filter_missing", "Native build-এ libass/ass filter প্রয়োজন।")
    if request.get("filter_backend", "software") != "software":
        raise FFV2Error("subtitle_hardware_filter_unsupported", "Subtitle rasterization-এর জন্য software filter backend দিন; hardware decode/encode ব্যবহার করা যায়।")
    plan = base(request, settings, caps, "transcode", restricted=restricted, allow_existing=allow_existing)
    source = input_path(request["subtitle_file"], settings, restricted=restricted)
    record, raw = asset(source, "subtitle", subtitles.MAX_BYTES)
    _, cue_info = subtitles.prepare(raw, source.suffix, request.get("start", 0), plan["expected"]["duration_seconds"], request.get("subtitle_offset", 0))
    selected = request.get("subtitle_font", "sans")
    if selected == "custom":
        if not {"font_file", "font_family"} <= set(request):
            raise FFV2Error("font_required", "Custom font-এর জন্য font_file ও font_family দিন।")
        font = input_path(request["font_file"], settings, restricted=restricted)
        family = request["font_family"]
    else:
        if "font_file" in request or "font_family" in request:
            raise FFV2Error("invalid_spec", "font_file/font_family-এর জন্য subtitle_font=custom দিন।")
        font_name, family = subtitles.BUILTIN_FONTS[selected]
        font = Path(font_name).resolve(strict=True)
    font_record, font_data = asset(font, "font", 20 * 1024**2)
    if font_data[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"ttcf"):
        raise FFV2Error("font_invalid", "Local TTF/OTF/TTC font প্রয়োজন।")
    subtitles.style_ass("", family, None, plan["expected"]["width"], plan["expected"]["height"])
    index = plan["argv"].index("-vf") + 1
    plan["argv"][index] += ",ass=filename=ffv2-subtitles.ass:fontsdir=ffv2-fonts"
    plan["assets"] = [record, font_record]
    plan["preparation"] = {"kind": "subtitle", "format": source.suffix.lower(), "family": family,
                           "font_size": request.get("font_size"), "cue_info": cue_info,
                           "start_seconds": request.get("start", 0), "offset_seconds": request.get("subtitle_offset", 0)}
    plan["warnings"].append("Subtitle source timeline থেকে selected range-এ shift হয়; ASS centisecond ও decoded frame timing প্রযোজ্য।")
    return finish(plan, request, settings, {"subtitle_file": str(source)})


def write_text_new(path, text):
    with Path(path).open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())


def prepare_inputs(plan, job, directory, settings, baseline, lock_fd, *, session=None):
    assert_sources(plan)
    preparation = plan["preparation"]
    if preparation["kind"] == "concat":
        text = "ffconcat version 1.0\n"
        for source in plan["sources"]:
            quoted = "'" + source["path"].replace("'", "'\\''") + "'"
            text += "file " + quoted + "\n"
        write_text_new(directory / "ffv2-inputs.ffconcat", text)
        return {"kind": "concat", "inputs": len(plan["sources"])}
    subtitle = next(item for item in plan["assets"] if item["kind"] == "subtitle")
    font = next(item for item in plan["assets"] if item["kind"] == "font")
    text, cue_info = subtitles.prepare(Path(subtitle["path"]).read_bytes(), preparation["format"], preparation["start_seconds"],
                                      plan["expected"]["duration_seconds"], preparation["offset_seconds"])
    font_directory = directory / "ffv2-fonts"
    font_directory.mkdir(mode=0o700)
    font_target = font_directory / ("selected" + Path(font["path"]).suffix)
    with Path(font["path"]).open("rb") as incoming, font_target.open("xb") as output:
        os.chmod(font_target, 0o600)
        shutil.copyfileobj(incoming, output, length=1024**2)
        output.flush()
        os.fsync(output.fileno())
    from .io import sha256_file
    if sha256_file(font_target) != font['sha256']:
        raise FFV2Error('font_copy_changed', 'Private font copy-এর checksum মেলেনি।')
    converted = None
    if preparation["format"] == ".srt":
        from .worker import supervised
        normalized = directory / "ffv2-normalized.srt"
        write_text_new(normalized, text)
        target = directory / "ffv2-converted.ass"
        command = [plan["binary"]["ffmpeg"], "-nostdin", "-hide_banner", "-v", "error", "-n", "-xerror",
                   "-max_alloc", "67108864", "-protocol_whitelist", "file", "-format_whitelist", "srt", "-f", "srt",
                   "-threads", "1", "-i", str(normalized), "-map", "0:s:0", "-c:s", "ass", "-f", "ass", "-fs", "4194304", str(target)]
        converted = supervised(command, "subtitle_prepare", job, directory, settings, baseline, lock_fd, target,
                               admission_budget=0, session=session)
        if not target.is_file() or not 0 < target.stat().st_size < 4 * 1024**2:
            raise FFV2Error("subtitle_conversion_failed", "Bounded ASS conversion পাওয়া যায়নি।")
        text = target.read_text(encoding="utf-8-sig")
    width, height = plan["expected"]["width"], plan["expected"]["height"]
    size = preparation["font_size"]
    if preparation["format"] == ".srt" and size is None:
        size = max(18, min(96, height * 0.045))
    text = subtitles.style_ass(text, preparation["family"], size, width, height, generated=preparation["format"] == ".srt")
    write_text_new(directory / "ffv2-subtitles.ass", text)
    assert_sources(plan)
    return {"kind": "subtitle", **cue_info, "font_sha256": font["sha256"], "conversion": converted}
