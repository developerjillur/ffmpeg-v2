import copy
import os
from pathlib import Path
import struct
from unittest.mock import patch

from ffv2.bindings import assert_sources
from ffv2.errors import FFV2Error
from ffv2.images import image_format, reject_animation
from ffv2.io import fingerprint
from ffv2.planner import build_plan, validate_spec
from ffv2.subtitles import prepare, style_ass
from test_safety import Workspace


class AdvancedWorkflowTests(Workspace):
    def second(self, *, audio=True, width=640):
        path = self.root / "second.dat"
        path.write_bytes(b"second controlled fixture")
        media = copy.deepcopy(self.metadata)
        media.update(path=str(path), fingerprint=fingerprint(path))
        media["video"]["width"] = width
        if not audio:
            media["audio"] = None
            media["streams"] = [media["video"]]
        return media

    def test_nested_track_schema_rejects_commands_boolean_gain_and_unbounded_arrays(self):
        for tracks in ([{"input": str(self.source), "argv": []}], [{"input": str(self.source), "gain_db": True}],
                       [{"input": str(self.source)}] * 8):
            with self.subTest(tracks=tracks), self.assertRaises(FFV2Error):
                validate_spec(self.spec(operation="audio_mix", tracks=tracks))
        with self.assertRaises(FFV2Error):
            validate_spec(self.spec(operation="image", background="#000000;movie=x"))

    def test_srt_range_offset_clamping_and_utf16(self):
        raw = "1\n00:00:01,000 --> 00:00:03,000\nবাংলা পরীক্ষা\n\n2\n00:00:04,500 --> 00:00:07,000\nSecond cue\n".encode("utf-16")
        text, info = prepare(raw, ".srt", 2, 4, 0.5)
        self.assertIn("00:00:00,000 --> 00:00:01,500", text)
        self.assertIn("00:00:03,000 --> 00:00:04,000", text)
        self.assertIn("বাংলা পরীক্ষা", text)
        self.assertEqual(info, {"source_cues": 2, "visible_cues": 2})
        with self.assertRaises(FFV2Error) as error:
            prepare(raw, ".srt", 20, 2)
        self.assertEqual(error.exception.code, "subtitle_range_empty")

    def test_ass_timing_preserves_commas_and_rejects_embedded_assets(self):
        source = "[Script Info]\nPlayResY: 360\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,24\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:02.00,0:00:04.00,Default,,0,0,0,,Hello, বাংলা\n"
        text, info = prepare(source.encode(), ".ass", 1, 2)
        self.assertIn("0:00:01.00,0:00:02.00", text)
        self.assertIn("Hello, বাংলা", text)
        styled = style_ass(text, "Bangla Sangam MN", 36, 640, 360)
        self.assertIn("Style: Default,Bangla Sangam MN,36", styled)
        with self.assertRaises(FFV2Error):
            prepare((source + "[Fonts]\nfontname: x").encode(), ".ass", 1, 2)

    def test_subtitle_plan_has_safe_filter_path_and_all_assets_are_bound(self):
        self.caps["filters"] += ["ass"]
        srt = self.root / "caption's file.srt"
        srt.write_text("1\n00:00:00,100 --> 00:00:01,900\nবাংলা পরীক্ষা\n")
        with patch("ffv2.planner.probe", return_value=self.metadata):
            plan = build_plan(self.spec(operation="subtitle", subtitle_file=str(srt), subtitle_font="bengali"), self.settings, self.caps)
        self.assertEqual(len(plan["assets"]), 2)
        graph = plan["argv"][plan["argv"].index("-vf") + 1]
        self.assertIn("ass=filename=ffv2-subtitles.ass:fontsdir=ffv2-fonts", graph)
        self.assertNotIn(str(srt), graph)
        before = srt.stat()
        srt.write_bytes(b"x" * before.st_size)
        os.utime(srt, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaises(FFV2Error) as error:
            assert_sources(plan)
        self.assertEqual(error.exception.code, "source_changed")

    def test_copy_concat_rejects_mismatched_extradata_and_secondary_source_change(self):
        second = self.second()
        for media in (self.metadata, second):
            for stream in media["streams"]:
                stream["extradata_hash"] = "SHA256:fixture"
        with patch("ffv2.concat.probe", side_effect=[self.metadata, second]), patch("ffv2.planner.probe", return_value=self.metadata):
            plan = build_plan(self.spec(operation="concat", output=str(self.root / "joined.mkv"),
                                       additional_inputs=[second["path"]], concat_mode="copy"), self.settings, self.caps)
        Path(second["path"]).write_bytes(b"changed secondary source")
        with self.assertRaises(FFV2Error):
            assert_sources(plan)
        second["video"]["extradata_hash"] = "SHA256:different"
        with patch("ffv2.concat.probe", side_effect=[self.metadata, second]), self.assertRaises(FFV2Error) as error:
            build_plan(self.spec(operation="concat", output=str(self.root / "copy.mkv"),
                                  additional_inputs=[second["path"]], concat_mode="copy"), self.settings, self.caps)
        self.assertEqual(error.exception.code, "concat_copy_incompatible")

    def test_normalized_concat_fills_missing_audio_and_has_exact_frame_contract(self):
        second = self.second(audio=False, width=320)
        self.caps["filters"] += ["concat", "scale", "pad", "fps", "tpad", "trim", "aresample", "aformat", "apad", "atrim", "anullsrc"]
        with patch("ffv2.concat.probe", side_effect=[self.metadata, second]), patch("ffv2.planner.probe", return_value=self.metadata):
            plan = build_plan(self.spec(operation="concat", additional_inputs=[second["path"]], encoder="software"), self.settings, self.caps)
        self.assertEqual(plan["expected"]["video_frames"], 120)
        self.assertEqual(plan["expected"]["audio_streams"], 1)
        graph = plan["argv"][plan["argv"].index("-filter_complex") + 1]
        self.assertIn("anullsrc", graph)
        self.assertEqual(plan["argv"].count("<STAGING_OUTPUT>"), 1)
        self.assertEqual(plan["argv"].count("-i"), 2)

    def test_mix_offsets_loops_and_gain_are_explicit_and_bounded(self):
        second = self.second()
        second["video"] = None
        second["streams"] = [second["audio"]]
        self.caps["filters"] += ["amix", "alimiter", "adelay", "apad", "atrim", "aresample", "aformat", "volume"]
        with patch("ffv2.mix.probe", return_value=second), patch("ffv2.planner.probe", return_value=self.metadata):
            plan = build_plan(self.spec(operation="audio_mix", output=str(self.root / "mix.wav"),
                    tracks=[{"input": second["path"], "offset": 0.5, "gain_db": -6, "loop": True}]), self.settings, self.caps)
        self.assertEqual(plan["expected"]["audio_samples"], 96000)
        graph = plan["argv"][plan["argv"].index("-filter_complex") + 1]
        self.assertIn("adelay=24000S", graph)
        self.assertIn("alimiter=limit=0.95:level=0:latency=1", graph)
        self.assertIn("-stream_loop", plan["argv"])

    def test_image_bit_depth_alpha_and_animation_contract(self):
        policy = image_format({"operation": "image", "output": "out.png"}, {"pix_fmt": "rgba64be"})
        self.assertEqual(policy["pix_fmt"], "rgba64be")
        self.assertTrue(policy["alpha"])
        self.assertEqual(image_format({"operation": "image", "output": "out.jpg"}, {"pix_fmt": "rgba"})["matte"], "#000000")
        webp = self.root / "animated.webp"
        webp.write_bytes(b"RIFF" + struct.pack("<I", 30) + b"WEBPVP8X" + struct.pack("<I", 10) + b"\x02" + b"\x00" * 9)
        with self.assertRaises(FFV2Error) as error:
            reject_animation(webp)
        self.assertEqual(error.exception.code, "image_animation_unsupported")
