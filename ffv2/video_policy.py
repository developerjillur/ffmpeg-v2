from __future__ import annotations

from .errors import FFV2Error
from pathlib import Path


def video_policy(request, video, caps):
    """স্পষ্ট interlace ও static PQ/HLG থেকে SDR policy; implicit tone mapping নয়।"""
    before_selection, before_scale, options, expected, warnings = [], [], [], {}, []
    kinds = " ".join(str(item.get("side_data_type", "")) for item in video.get("side_data_list", [])).lower()
    if any(name in kinds for name in ("dovi", "dolby", "hdr10+", "dynamic hdr")):
        raise FFV2Error("dynamic_hdr_unsupported", "Signalled dynamic HDR/Dolby Vision এই static conversion policy-তে অনুমোদিত নয়।")
    interlaced = video.get("field_order") not in (None, "unknown", "progressive")
    if interlaced and request.get("deinterlace", "off") != "bwdif":
        raise FFV2Error("interlaced_policy_required", "Interlaced source-এর জন্য deinterlace=bwdif দিন।")
    if request.get("deinterlace") == "bwdif":
        if "bwdif" not in caps["filters"]:
            raise FFV2Error("filter_missing", "এই build-এ bwdif নেই।")
        before_selection.append("bwdif=mode=send_frame:parity=auto:deint=interlaced")
        expected["progressive"] = True
        warnings.append("bwdif send_frame interlaced frames deinterlace করে; field-rate doubling করা হয় না।")
    hdr = video.get("color_transfer") in ("smpte2084", "arib-std-b67") or video.get("color_primaries") == "bt2020"
    colour_known = all(video.get(key) not in (None,'unknown','unspecified','reserved') for key in ('color_primaries','color_transfer','color_space','color_range'))
    if not colour_known:
        warnings.append('Source colour metadata অসম্পূর্ণ; filename দেখে HDR/PQ/HLG infer করা হয়নি। Known HDR হলে source signalling আগে যাচাই করুন।')
    if hdr:
        if request.get("hdr_policy", "reject") != "tone_map":
            raise FFV2Error("hdr_policy_required", "HDR source-এর জন্য hdr_policy=tone_map ও source_peak_nits দিন; remux-এ conversion লাগে না।")
        image = request["operation"] in ("frame", "contact_sheet", "image")
        if image and Path(request["output"]).suffix.lower() != ".png":
            raise FFV2Error("hdr_operation_unsupported", "HDR image tone map-এর জন্য PNG output দিন।")
        primaries, matrix = video.get("color_primaries"), video.get("color_space")
        known_matrix = matrix in ("bt2020nc", "gbr") if primaries == "bt2020" else matrix in ("bt2020nc", "bt709", "gbr")
        if (video.get("color_transfer") not in ("smpte2084", "arib-std-b67") or primaries not in ("bt2020", "smpte431", "smpte432") or
                not known_matrix or video.get("color_range") not in ("tv", "pc")):
            raise FFV2Error("hdr_metadata_required", "Explicit PQ/HLG, BT.2020/P3 primaries, supported matrix ও known range প্রয়োজন।")
        if image and video.get("pix_fmt", "").startswith(("rgba", "bgra", "argb", "abgr", "gbrap", "yuva", "ya")):
            raise FFV2Error("hdr_alpha_unsupported", "HDR alpha-এর separate premultiplication policy প্রয়োজন; implicit alpha loss অনুমোদিত নয়।")
        if "source_peak_nits" not in request:
            raise FFV2Error("hdr_peak_required", "Tone mapping-এর জন্য source_peak_nits স্পষ্টভাবে দিন।")
        missing = {"zscale", "tonemap", "sidedata", "setparams"} - set(caps["filters"])
        if missing:
            raise FFV2Error("filter_missing", "Tone-map filter build-এ নেই।", details={"filters": sorted(missing)})
        peak = request["source_peak_nits"] / 100
        before_scale += ["zscale=transfer=linear:npl=100", "format=gbrpf32le", "zscale=primaries=bt709",
                         "setparams=range=full:color_primaries=bt709:color_trc=linear:colorspace=bt709",
                         f"tonemap=tonemap=hable:desat=2:peak={peak:.9g}"]
        if image:
            depth = request.get("image_bit_depth", 16)
            before_scale += ["zscale=transfer=iec61966-2-1:matrix=gbr:range=full", "format=" + ("rgb48be" if depth == 16 else "rgb24")]
        else:
            before_scale += ["zscale=transfer=bt709:matrix=bt709:range=limited", "format=yuv420p"]
        before_scale += [
                         "sidedata=mode=delete:type=MASTERING_DISPLAY_METADATA",
                         "sidedata=mode=delete:type=CONTENT_LIGHT_LEVEL",
                         "sidedata=mode=delete:type=ICC_PROFILE"]
        if image:
            before_scale += ["setparams=range=full:color_primaries=bt709:color_trc=iec61966-2-1:colorspace=gbr"]
            options += ["-color_primaries", "bt709", "-color_trc", "iec61966-2-1", "-colorspace", "0", "-color_range", "pc"]
            expected.update(color_primaries="bt709", color_transfer="iec61966-2-1", color_space="gbr", color_range="pc")
        else:
            before_scale += ["setparams=range=limited:color_primaries=bt709:color_trc=bt709:colorspace=bt709"]
            options += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"]
            expected.update(color_primaries="bt709", color_transfer="bt709", color_space="bt709", color_range="tv")
        warnings.append("Explicit Hable tone map: known PQ/HLG থেকে 100-nit SDR; PNG-তে full-range sRGB, video-তে limited BT.709।")
    elif request.get("hdr_policy") == "tone_map" or "source_peak_nits" in request:
        if not colour_known:
            raise FFV2Error('hdr_metadata_required','Source colour signalling অসম্পূর্ণ; HDR filename বা peak value দিয়ে missing primaries/transfer/matrix/range পূরণ করা যায় না।')
        raise FFV2Error("hdr_policy_conflict", "SDR source-এ HDR tone-map/peak field প্রযোজ্য নয়।")
    return before_selection, before_scale, options, expected, warnings
