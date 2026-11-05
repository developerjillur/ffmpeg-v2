from ffv2.errors import FFV2Error
from test_safety import Workspace


class HardwareScalingTests(Workspace):
    def setUp(self):
        super().setUp()
        self.metadata["video"].update(pix_fmt="yuv420p", color_range="tv")
        self.caps["filters"] += ["hwdownload", "scale_vt"]

    def hardware_plan(self, **kwargs):
        return self.plan(encoder="videotoolbox", decode="videotoolbox", filter_backend="videotoolbox", **kwargs)

    def test_explicit_hardware_frames_avoid_download_and_cpu_scale(self):
        plan = self.hardware_plan()
        filters = plan["argv"][plan["argv"].index("-vf") + 1]
        self.assertEqual(filters, "scale_vt=w=640:h=360,setsar=1")
        self.assertNotIn("hwdownload", filters)
        self.assertEqual(plan["argv"][plan["argv"].index("-pix_fmt") + 1], "videotoolbox_vld")
        self.assertTrue(plan["expected"]["hardware_decode_required"])
        self.assertTrue(plan["expected"]["hardware_filter_required"])
        self.assertFalse(plan["hardware_runtime_verified"])

    def test_default_keeps_software_filter_path(self):
        plan = self.plan(encoder="videotoolbox", decode="videotoolbox")
        self.assertIn("hwdownload,format=nv12,scale=", plan["argv"][plan["argv"].index("-vf") + 1])

    def test_unsupported_surfaces_geometry_and_cpu_requests_are_refused(self):
        cases = ({"pix_fmt": "yuv420p10le"}, {"sample_aspect_ratio": "4:3"}, {"color_range": "pc"},
                 {"side_data_list": [{"rotation": 90}]})
        for change in cases:
            original = dict(self.metadata["video"])
            self.metadata["video"].update(change)
            with self.subTest(change=change), self.assertRaises(FFV2Error) as error:
                self.hardware_plan()
            self.assertEqual(error.exception.code, "hardware_filter_unsupported")
            self.metadata["video"].clear()
            self.metadata["video"].update(original)
        for change in ({"decode": "software"}, {"encoder": "software"}):
            with self.assertRaises(FFV2Error):
                self.plan(**{"encoder": "videotoolbox", "decode": "videotoolbox", "filter_backend": "videotoolbox", **change})
