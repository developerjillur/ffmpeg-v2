import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from performance_phase11 import speed_groups,validate,runtime_binding
from collect_release_acceptance import performance_check


class ConditionedPromotionTests(unittest.TestCase):
    def evidence(self,pipeline=False):
        keys=[p+'/load'+str(load) for p in (('hd60',) if pipeline else ('hd60','raw30')) for load in (0,2)]
        row={'blocks':9,'n_per_engine':18,'speedup_proven':True,'paired_geometric_mean_ratio':.96,'whole_block_95_percent':[.94,.98]}
        return {'status':'completed','phase':11,'release_performance_accepted':True,'insufficient_groups':[],
            'accepted_blocks':{key:9 for key in keys},'comparisons':{key:{label:copy.deepcopy(row) for label in ('original','stock')} for key in keys}}

    def test_one_unproven_group_cannot_hide_behind_pass_flag(self):
        evidence=self.evidence();evidence['comparisons']['raw30/load2']['stock']['whole_block_95_percent'][1]=1.01
        with self.assertRaises(RuntimeError):speed_groups(evidence,pipeline=False)

    def test_missing_group_or_short_sample_is_not_promotion_evidence(self):
        evidence=self.evidence();del evidence['comparisons']['raw30/load0']
        with self.assertRaises(RuntimeError):speed_groups(evidence,pipeline=False)
        evidence=self.evidence();evidence['comparisons']['hd60/load0']['original']['n_per_engine']=16
        with self.assertRaises(RuntimeError):speed_groups(evidence,pipeline=False)

    def test_both_workflow_load_states_are_required(self):
        evidence=self.evidence(pipeline=True);del evidence['comparisons']['hd60/load2']
        with self.assertRaises(RuntimeError):speed_groups(evidence,pipeline=True)

    def test_direct_analysis_alone_cannot_enter_release_collector(self):
        with self.assertRaisesRegex(RuntimeError,'Combined direct'):
            performance_check(self.evidence(),{}, {})

    def test_incomplete_or_unaccepted_result_is_rejected_before_io(self):
        for value in ({'status':'running','phase':11,'release_performance_accepted':True},
                      {'status':'completed','phase':11,'release_performance_accepted':False}):
            with self.assertRaisesRegex(RuntimeError,'Complete Phase 11'):validate(value,{}, {})

    def test_workflow_probe_change_invalidates_runtime_binding(self):
        timing={'configurations':{'stock':{'ffmpeg':'/native/ffmpeg','ffprobe':'/native/ffprobe'}},
                'engine_files':{'stock':{'/native/ffmpeg':'encoder','/native/ffprobe':'probe'}}}
        quality={'configurations':{'stock':'/native/ffmpeg'},'engine_files':{'stock':{'/native/ffmpeg':'encoder'}}}
        with patch('performance_phase11.library_closure',return_value={'/native/ffmpeg':'encoder','/native/ffprobe':'changed'}) as closure:
            with self.assertRaisesRegex(RuntimeError,'runtime closure changed'):runtime_binding(timing,quality,pipeline=True)
            closure.assert_called_once_with([Path('/native/ffmpeg'),Path('/native/ffprobe')])

    def test_unchanged_workflow_and_quality_closures_bind(self):
        files={'/native/ffmpeg':'encoder','/native/ffprobe':'probe'}
        timing={'configurations':{'candidate':{'ffmpeg':'/native/ffmpeg','ffprobe':'/native/ffprobe'}},'engine_files':{'candidate':files}}
        quality={'configurations':{'candidate':'/native/ffmpeg'},'engine_files':{'candidate':{'/native/ffmpeg':'encoder'}}}
        with patch('performance_phase11.library_closure',return_value=files):runtime_binding(timing,quality,pipeline=True)
