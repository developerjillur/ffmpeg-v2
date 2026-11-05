from unittest.mock import patch

from ffv2.errors import FFV2Error
from ffv2.planner import build_plan
from ffv2.worker import validate_metadata
from test_safety import Workspace


class VideoPolicyTests(Workspace):
    def setUp(self):
        super().setUp()
        self.caps["filters"] += ["bwdif", "zscale", "tonemap", "sidedata", "setparams"]

    def test_interlace_requires_explicit_policy_and_filter_runs_before_selection(self):
        self.metadata["video"]["field_order"] = "tt"
        with self.assertRaises(FFV2Error) as caught:
            self.plan()
        self.assertEqual(caught.exception.code, "interlaced_policy_required")
        plan = self.plan(operation="contact_sheet", output=str(self.root / "sheet.jpg"), deinterlace="bwdif", count=4)
        filters = plan["argv"][plan["argv"].index("-vf") + 1]
        self.assertLess(filters.index("bwdif"), filters.index("select="))
        self.assertTrue(plan["expected"]["progressive"])

    def test_unknown_colour_is_not_mislabeled_as_known_sdr_for_hdr_requests(self):
        with self.assertRaises(FFV2Error) as caught:
            self.plan(hdr_policy='tone_map',source_peak_nits=1000)
        self.assertEqual(caught.exception.code,'hdr_metadata_required')
        self.metadata['video'].update(color_primaries='bt709',color_transfer='bt709',color_space='bt709',color_range='tv')
        with self.assertRaises(FFV2Error) as caught:
            self.plan(hdr_policy='tone_map',source_peak_nits=1000)
        self.assertEqual(caught.exception.code,'hdr_policy_conflict')

    def test_hdr_policy_rejects_missing_peak_unknown_matrix_and_dynamic_metadata(self):
        self.metadata["video"].update(color_transfer="smpte2084", color_primaries="bt2020", color_space="bt2020nc", color_range="tv")
        cases = [(dict(), "hdr_policy_required"), ({"hdr_policy":"tone_map"}, "hdr_peak_required")]
        for fields, code in cases:
            with self.subTest(code=code), self.assertRaises(FFV2Error) as caught:
                self.plan(**fields)
            self.assertEqual(caught.exception.code, code)
        plan = self.plan(hdr_policy="tone_map", source_peak_nits=1000)
        self.assertEqual(plan["expected"]["color_transfer"], "bt709")
        self.assertIn("sidedata=mode=delete:type=MASTERING_DISPLAY_METADATA", plan["display_command"])
        filters = plan["argv"][plan["argv"].index("-vf") + 1]
        self.assertLess(filters.index("color_trc=linear:colorspace=bt709"), filters.index("tonemap="))
        self.metadata["video"]["side_data_list"] = [{"side_data_type":"DOVI configuration record"}]
        with self.assertRaises(FFV2Error) as caught:
            self.plan(hdr_policy="tone_map", source_peak_nits=1000)
        self.assertEqual(caught.exception.code, "dynamic_hdr_unsupported")
        self.metadata["video"].pop("side_data_list")
        self.metadata["video"]["color_space"] = "unknown"
        with self.assertRaises(FFV2Error) as caught:
            self.plan(hdr_policy="tone_map", source_peak_nits=1000)
        self.assertEqual(caught.exception.code, "hdr_metadata_required")

    def test_sparse_sampling_is_bounded_and_auto_uses_seeks_only_for_long_intervals(self):
        self.metadata["duration_seconds"] = 600
        plan = self.plan(operation="contact_sheet", output=str(self.root/"sparse.jpg"), count=8)
        self.assertEqual(plan["expected"]["sampling_method"], "seek")
        self.assertEqual(plan["argv"].count("-i"), 8)
        self.assertIn("xstack=inputs=8", plan["display_command"])
        dense = self.plan(operation="contact_sheet", output=str(self.root/"dense.jpg"), count=16)
        self.assertEqual(dense["expected"]["sampling_method"], "single_pass")
        with self.assertRaises(FFV2Error) as caught:
            self.plan(operation="contact_sheet", output=str(self.root/"invalid.jpg"), count=9, sampling="seek")
        self.assertEqual(caught.exception.code, "seek_sampling_unsupported")

    def test_explicit_hardware_decode_requires_hardware_frames_instead_of_unverified_fallback(self):
        self.caps["filters"].append("hwdownload")
        self.metadata["video"]["pix_fmt"] = "yuv420p10le"
        plan = self.plan(decode="videotoolbox")
        self.assertIn("-hwaccel_output_format", plan["argv"])
        filters = plan["argv"][plan["argv"].index("-vf") + 1]
        self.assertTrue(filters.startswith("hwdownload,format=p010le,"))
        self.assertTrue(plan["expected"]["hardware_decode_required"])
        self.metadata["video"]["pix_fmt"] = "yuv444p12le"
        with self.assertRaises(FFV2Error) as caught:
            self.plan(decode="videotoolbox")
        self.assertEqual(caught.exception.code, "hardware_surface_unsupported")
