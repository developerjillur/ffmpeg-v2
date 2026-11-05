import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('phase9_analysis',Path(__file__).resolve().parents[1]/'scripts/analyze_phase9.py')
analysis=importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class Phase9AnalysisTests(unittest.TestCase):
    def rows(self, ratios):
        return [dict(warmup=False,block=b,label=label,seconds=10*(ratio if label=='native' else 1))
                for b,ratio in enumerate(ratios) for label in ('native','stock','stock','native')]

    def test_uniform_improvement_has_matching_interval(self):
        result=analysis.paired_blocks(self.rows([.9,.9,.9]),draws=200)
        self.assertEqual(result['native_stock_ratio'],.9)
        self.assertEqual(result['block_bootstrap_95_percent'],[.9,.9])
        self.assertTrue(result['native_faster_supported'])

    def test_reversing_epochs_do_not_support_speed_claim(self):
        result=analysis.paired_blocks(self.rows([.8,1.2]),draws=200)
        self.assertFalse(result['native_faster_supported'])
        self.assertFalse(result['stock_faster_supported'])

    def test_warmup_cannot_change_measurement(self):
        rows=self.rows([1,1]);rows.append(dict(warmup=True,block=-1,label='native',seconds=100000))
        result=analysis.paired_blocks(rows,draws=200)
        self.assertEqual(result['native_stock_ratio'],1)
        self.assertEqual(result['n_per_engine'],4)

    def test_missing_control_is_rejected(self):
        rows=self.rows([1,1]);rows.pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):analysis.paired_blocks(rows)

    def test_single_block_is_not_confirmation(self):
        with self.assertRaisesRegex(ValueError,'At least two'):analysis.paired_blocks(self.rows([1]))
