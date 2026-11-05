from unittest.mock import patch

from ffv2.errors import FFV2Error
from test_safety import Workspace


class ThreadTuningTests(Workspace):
    def test_hd_defaults_use_accepted_pools_and_preserve_explicit_requests(self):
        self.metadata['duration_seconds'] = 120
        self.metadata['video'].update(width=1920, height=1080, pix_fmt='yuv420p', r_frame_rate='30/1')
        with patch('ffv2.darwin.cpu_brand', return_value='Apple M4 Max'):
            plan = self.plan(encoder='software', fps=30)
            self.assertEqual(plan['runtime_tuning']['profile'], 'm4_max_hd_software')
            self.assertEqual(tuple(plan['runtime_tuning'][k] for k in
                ('encoder_threads','decoder_threads','filter_threads','validation_threads')), (8,2,2,8))
            self.assertEqual(plan['runtime_tuning']['encode_thread_budget'], 13)
            for override in ({'threads':1}, {'threads':4,'decoder_threads':4,'filter_threads':4},
                             {'decoder_threads':4}, {'filter_threads':4}, {'validation_threads':2}):
                with self.subTest(override=override):
                    tuning = self.plan(encoder='software', fps=30, **override)['runtime_tuning']
                    self.assertNotEqual(tuning['profile'], 'm4_max_hd_software')
                    for key,value in override.items():
                        self.assertEqual(tuning['encoder_threads' if key=='threads' else key], value)

    def test_hd_profile_preserves_unmeasured_pipelines(self):
        from ffv2.tuning import pools
        self.metadata['duration_seconds'] = 120
        self.metadata['video'].update(width=1920, height=1080, pix_fmt='yuv420p', r_frame_rate='30/1')
        source = self.metadata['video']
        request = self.spec(encoder='software', fps=30)
        with patch('ffv2.darwin.cpu_brand', return_value='Apple M4 Max'):
            for change in ({'codec_name':'hevc'}, {'pix_fmt':'yuv420p10le'}, {'r_frame_rate':'60/1'},
                           {'field_order':'tt'}, {'color_transfer':'smpte2084'}, {'sample_aspect_ratio':'4:3'},
                           {'side_data_list':[{'rotation':180}]}):
                with self.subTest(source=change):
                    tuning = pools(request, {**source, **change}, 120, self.caps, width=1920, height=1080)
                    self.assertNotEqual(tuning['profile'], 'm4_max_hd_software')
            for change in ({'rate_control':'bitrate'}, {'video_bitrate':6000000}, {'checkpoint_seconds':10},
                           {'fps':24}, {'decode':'videotoolbox'}, {'deinterlace':'bwdif'}, {'hdr_policy':'tone_map'}):
                with self.subTest(request=change):
                    self.assertNotEqual(pools({**request, **change}, source, 120, self.caps,
                                             width=1920,height=1080)['profile'], 'm4_max_hd_software')
            self.assertNotEqual(pools(request,source,59,self.caps,width=1920,height=1080)['profile'], 'm4_max_hd_software')
            self.assertNotEqual(pools(request,{**source,'width':3840,'height':2160},120,self.caps,
                                      width=1920,height=1080)['profile'], 'm4_max_hd_software')

    def test_liveaction_vp8_uses_accepted_pools(self):
        self.metadata['duration_seconds'] = 120
        self.metadata['video'].update(codec_name='vp8', width=1920, height=800, pix_fmt='yuv420p',
                                      avg_frame_rate='24/1', r_frame_rate='24/1')
        with patch('ffv2.darwin.cpu_brand', return_value='Apple M4 Max'):
            tuning = self.plan(encoder='software', fps=24)['runtime_tuning']
            self.assertEqual(tuning['profile'],'m4_max_hd_software')
            self.assertEqual(tuning['encoder_threads'],8)
            self.assertEqual(tuning['validation_threads'],8)

    def test_bounded_higher_software_concurrency_and_validation(self):
        for threads in (6, 8):
            plan = self.plan(encoder='software', threads=threads, decoder_threads=2, filter_threads=2, validation_threads=8)
            self.assertEqual(plan['runtime_tuning']['encoder_threads'], threads)
            self.assertEqual(plan['runtime_tuning']['validation_threads'], 8)
            self.assertEqual(plan['runtime_tuning']['encode_thread_budget'], threads+5)
            self.assertIn(str(threads), plan['argv'])

    def test_higher_concurrency_keeps_operation_and_total_budget_guards(self):
        for parameters in ({'encoder':'videotoolbox','threads':8},
                           {'operation':'frame','output':str(self.root/'frame.jpg'),'threads':8},
                           {'encoder':'software','threads':8,'decoder_threads':4,'filter_threads':4},
                           {'encoder':'software','validation_threads':9}):
            with self.subTest(parameters=parameters), self.assertRaises(FFV2Error):
                self.plan(**parameters)

    def test_separate_pools_are_typed_and_kept_in_plan(self):
        plan = self.plan(encoder="software", threads=4, decoder_threads=2, filter_threads=1, validation_threads=4)
        self.assertEqual(plan["argv"][plan["argv"].index("-threads") + 1], "2")
        self.assertEqual(plan["argv"][plan["argv"].index("-threads:v") + 1], "4")
        self.assertEqual(plan["runtime_tuning"]["validation_threads"], 4)
        self.assertEqual(plan["runtime_tuning"]["encode_thread_budget"], 8)
        for name in ("decoder_threads", "filter_threads", "validation_threads"):
            with self.subTest(name=name), self.assertRaises(FFV2Error):
                self.plan(**{name: True})

    def test_calibrated_profile_is_machine_and_workload_scoped(self):
        self.metadata["duration_seconds"] = 120
        self.metadata["video"].update(width=1920, height=1080, pix_fmt="yuv420p")
        with patch("ffv2.tuning.M4_LONG_PROFILE_ENABLED", True), patch("ffv2.darwin.cpu_brand", return_value="Apple M4 Max"):
            plan = self.plan(encoder="software")
            self.assertEqual(plan["runtime_tuning"]["profile"], "m4_max_long_software")
            self.assertEqual(plan["runtime_tuning"]["encoder_threads"], 4)
            self.assertEqual(plan["runtime_tuning"]["decoder_threads"], 2)
            self.assertEqual(plan["runtime_tuning"]["validation_threads"], 4)
            self.assertEqual(self.plan(encoder="software", threads=1)["runtime_tuning"]["encoder_threads"], 1)
            self.assertEqual(self.plan(encoder="videotoolbox")["runtime_tuning"]["profile"], "conservative")
            self.assertEqual(self.plan(encoder="software", duration=59)["runtime_tuning"]["profile"], "conservative")
            self.metadata["video"].update(width=3840, height=2160)
            resized = self.plan(encoder="software", max_width=1920, max_height=1080)
            self.assertEqual(resized["runtime_tuning"]["filter_threads"], 4)
            self.assertEqual(resized["runtime_tuning"]["profile"], "m4_max_long_software_resize")
        with patch("ffv2.tuning.M4_LONG_PROFILE_ENABLED", True), patch("ffv2.darwin.cpu_brand", return_value="Different CPU"):
            self.assertEqual(self.plan(encoder="software")["runtime_tuning"]["encoder_threads"], 2)

    def test_sparse_multi_input_total_is_bounded(self):
        self.metadata["duration_seconds"] = 600
        with self.assertRaises(FFV2Error) as error:
            self.plan(operation="contact_sheet", output=str(self.root / "sheet.jpg"), count=8, sampling="seek",
                      decoder_threads=4, filter_threads=4)
        self.assertEqual(error.exception.code, "thread_budget_exceeded")
