"""SRT/ASS cue timing ও local font assets-এর সীমিত প্রস্তুতি।"""
from __future__ import annotations

import re
from pathlib import Path

from .errors import FFV2Error

MAX_BYTES = 1024**2
MAX_CUES = 10000
SRT_TIME = r"(\d{1,3}):(\d{2}):(\d{2})[,.](\d{1,3})"
BUILTIN_FONTS = {
    "sans": ("/System/Library/Fonts/Supplemental/Arial.ttf", "Arial"),
    "bengali": ("/System/Library/Fonts/Supplemental/Bangla Sangam MN.ttc", "Bangla Sangam MN"),
}


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise FFV2Error("subtitle_size_exceeded", "Subtitle সর্বোচ্চ 1 MiB।")
    try:
        text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    except UnicodeError as error:
        raise FFV2Error("subtitle_encoding_invalid", "UTF-8 অথবা BOM-সহ UTF-16 subtitle দিন।") from error
    if "\x00" in text:
        raise FFV2Error("subtitle_invalid", "Subtitle text-এ NUL গ্রহণযোগ্য নয়।")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def milliseconds(parts):
    hour, minute, second, fraction = parts
    if int(minute) > 59 or int(second) > 59 or int(hour) > 24:
        raise FFV2Error("subtitle_time_invalid", "Subtitle clock range ঠিক করুন।")
    return ((int(hour) * 60 + int(minute)) * 60 + int(second)) * 1000 + int(fraction.ljust(3, "0"))


def srt_time(value):
    second, fraction = divmod(value, 1000)
    minute, second = divmod(second, 60)
    hour, minute = divmod(minute, 60)
    return f"{hour:02}:{minute:02}:{second:02},{fraction:03}"


def shifted_srt(text, start, duration, offset=0):
    shifted = []
    count = 0
    shift = round((offset - start) * 1000)
    end = round(duration * 1000)
    for block in re.split(r"\n[ \t]*\n", text.strip()):
        lines = block.splitlines()
        if lines and lines[0].strip().isdigit():
            lines = lines[1:]
        match = re.fullmatch(SRT_TIME + r"\s*-->\s*" + SRT_TIME + r"(?:\s+([XY12:0-9 ]+))?", lines[0].strip()) if lines else None
        if not match or len(lines) < 2:
            raise FFV2Error("subtitle_invalid", "SRT cue ও timestamp format ঠিক করুন।")
        begin, finish = milliseconds(match.groups()[:4]), milliseconds(match.groups()[4:8])
        if finish <= begin:
            raise FFV2Error("subtitle_time_invalid", "Subtitle cue-এর end অবশ্যই start-এর পরে হবে।")
        if sum(len(line) for line in lines[1:]) > 8192:
            raise FFV2Error("subtitle_cue_size_exceeded", "এক cue-এর text সর্বোচ্চ 8192 character।")
        count += 1
        if count > MAX_CUES:
            raise FFV2Error("subtitle_count_exceeded", "Subtitle cue count সীমার বাইরে।")
        begin, finish = max(0, begin + shift), min(end, finish + shift)
        if finish <= begin:
            continue
        suffix = " " + match.group(9) if match.group(9) else ""
        shifted.append(str(len(shifted) + 1) + "\n" + srt_time(begin) + " --> " + srt_time(finish) + suffix + "\n" + "\n".join(lines[1:]))
    if not shifted:
        raise FFV2Error("subtitle_range_empty", "এই media range-এ কোনো subtitle cue নেই।")
    return "\n\n".join(shifted) + "\n", {"source_cues": count, "visible_cues": len(shifted)}


def ass_time(value):
    second, fraction = divmod(value, 100)
    minute, second = divmod(second, 60)
    hour, minute = divmod(minute, 60)
    return f"{hour}:{minute:02}:{second:02}.{fraction:02}"


def shifted_ass(text, start, duration, offset=0):
    section = ""
    fields = ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]
    output, count, visible = [], 0, 0
    shift, end = round((offset - start) * 100), round(duration * 100)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            section = stripped.lower()
            if section in ("[fonts]", "[graphics]"):
                raise FFV2Error("subtitle_attachment_unsupported", "ASS attachments-এর বদলে explicit local font asset দিন।")
        if section == "[events]" and stripped.lower().startswith("format:"):
            fields = [x.strip().lower() for x in stripped.split(":", 1)[1].split(",")]
            if not {"start", "end", "text"} <= set(fields) or fields[-1] != "text":
                raise FFV2Error("subtitle_invalid", "ASS Events Format গ্রহণযোগ্য নয়।")
        if section == "[events]" and stripped.lower().startswith("dialogue:"):
            parts = stripped.split(":", 1)[1].lstrip().split(",", len(fields) - 1)
            if len(parts) != len(fields):
                raise FFV2Error("subtitle_invalid", "ASS Dialogue field count মেলেনি।")
            if len(parts[fields.index("text")]) > 8192:
                raise FFV2Error("subtitle_cue_size_exceeded", "এক ASS cue-এর text সর্বোচ্চ 8192 character।")
            times = []
            for name in ("start", "end"):
                raw = parts[fields.index(name)].strip()
                match = re.fullmatch(r"(\d{1,3}):(\d{2}):(\d{2})\.(\d{2})", raw)
                if not match:
                    raise FFV2Error("subtitle_time_invalid", "ASS cue timestamp ঠিক করুন।")
                times.append(milliseconds(match.groups()) // 10)
            if times[1] <= times[0]:
                raise FFV2Error("subtitle_time_invalid", "ASS cue-এর end start-এর পরে হবে।")
            count += 1
            if count > MAX_CUES:
                raise FFV2Error("subtitle_count_exceeded", "ASS cue count সীমার বাইরে।")
            begin, finish = max(0, times[0] + shift), min(end, times[1] + shift)
            if finish <= begin:
                continue
            parts[fields.index("start")], parts[fields.index("end")] = ass_time(begin), ass_time(finish)
            line = "Dialogue: " + ",".join(parts)
            visible += 1
        output.append(line)
    if not visible:
        raise FFV2Error("subtitle_range_empty", "এই range-এ ASS Dialogue cue নেই।")
    return "\n".join(output) + "\n", {"source_cues": count, "visible_cues": visible}


def prepare(raw, suffix, start, duration, offset=0):
    text = decode(raw)
    if suffix.lower() == ".srt":
        return shifted_srt(text, start, duration, offset)
    if suffix.lower() in (".ass", ".ssa"):
        return shifted_ass(text, start, duration, offset)
    raise FFV2Error("subtitle_format_unsupported", "Local SRT, ASS অথবা SSA subtitle দিন।")


def style_ass(text, family, font_size, width, height, *, generated=False):
    if not re.fullmatch(r"[^\x00-\x1f,{}\\]{1,64}", family):
        raise FFV2Error("font_family_invalid", "Font family name গ্রহণযোগ্য নয়।")
    if generated:
        text = re.sub(r"(?mi)^[ \t]*PlayResX:.*$", "PlayResX: " + str(width), text)
        text = re.sub(r"(?mi)^[ \t]*PlayResY:.*$", "PlayResY: " + str(height), text)
    resolution = re.search(r"(?mi)^[ \t]*PlayResY:\s*(\d+)", text)
    play_height = int(resolution.group(1)) if resolution else height
    fields, section, output = [], "", []
    for line in text.splitlines():
        stripped = line.lstrip()
        if line.strip().startswith("["):
            section = line.strip().lower()
            if section == "[v4+ styles]":
                fields = "name,fontname,fontsize,primarycolour,secondarycolour,outlinecolour,backcolour,bold,italic,underline,strikeout,scalex,scaley,spacing,angle,borderstyle,outline,shadow,alignment,marginl,marginr,marginv,encoding".split(",")
            elif section == "[v4 styles]":
                fields = "name,fontname,fontsize,primarycolour,secondarycolour,tertiarycolour,backcolour,bold,italic,borderstyle,outline,shadow,alignment,marginl,marginr,marginv,alphalevel,encoding".split(",")
        if section in ("[v4+ styles]", "[v4 styles]"):
            if stripped.lower().startswith("format:"):
                fields = [x.strip().lower() for x in stripped.split(":", 1)[1].split(",")]
            if stripped.lower().startswith("style:") and "fontname" in fields:
                values = stripped.split(":", 1)[1].lstrip().split(",")
                if len(values) != len(fields):
                    raise FFV2Error("subtitle_invalid", "ASS style field count মেলেনি।")
                values[fields.index("fontname")] = family
                if font_size is not None and "fontsize" in fields:
                    values[fields.index("fontsize")] = format(font_size * play_height / height, ".6g")
                line = "Style: " + ",".join(values)
        output.append(line)
    return "\n".join(output) + "\n"
