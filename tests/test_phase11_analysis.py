import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from analyze_phase11 import paired
from admission_phase11 import window_valid,readiness


class ConditionedAcceptanceTests(unittest.TestCase):
    def rows(self,ratios):
        return [dict(block=block,label=label,seconds=base*(ratio if label=='candidate' else 1))
                for block,ratio in enumerate(ratios) for label in ('candidate','stock')
                for base in (10*(block+1),12*(block+1))]

    def test_block_pairs_cancel_shared_load_changes(self):
        value=paired(self.rows([.9]*9),'stock',draws=1000)
        self.assertAlmostEqual(value['paired_geometric_mean_ratio'],.9)
        self.assertTrue(value['speedup_proven'])
        self.assertEqual(value['blocks'],9)

    def test_mixed_direction_cannot_claim_reliable_speedup(self):
        value=paired(self.rows([.8,1.25,1]*3),'stock',draws=1000)
        self.assertFalse(value['speedup_proven'])
        self.assertLess(value['whole_block_95_percent'][0],1)
        self.assertGreater(value['whole_block_95_percent'][1],1)

    def test_incomplete_pair_cannot_be_silently_dropped(self):
        with self.assertRaises(ValueError):paired(self.rows([.9]*9)[:-1],'stock',draws=1000)

    def test_invalid_duration_cannot_be_used_for_speedup(self):
        rows=self.rows([.9]*9);rows[0]['seconds']=0
        with self.assertRaises(ValueError):paired(rows,'stock',draws=1000)

    def test_detector_accepts_stable_saturation_and_rejects_bursts(self):
        samples=[dict(processors=14,capacity=14,busy=13.95) for _ in range(8)]
        self.assertTrue(window_valid(samples))
        samples[3]['busy']=10
        self.assertFalse(window_valid(samples))

    def test_detector_rejects_stale_counters_or_short_window(self):
        samples=[dict(processors=14,capacity=14,busy=4) for _ in range(8)]
        self.assertFalse(window_valid(samples[:-1]))
        samples[0]['capacity']=28
        self.assertFalse(window_valid(samples))

    def test_probe_readiness_does_not_label_bursts_stable(self):
        samples=[dict(processors=14,capacity=14,busy=v) for v in (2,5,3,6,2,5,3,6)]
        self.assertIsNone(readiness(samples,14))
        self.assertEqual(readiness(samples,15),'exploratory_block')
        self.assertFalse(window_valid(samples))

    def test_probe_cannot_bypass_stale_cpu_counter(self):
        samples=[dict(processors=14,capacity=28,busy=6) for _ in range(8)]
        self.assertIsNone(readiness(samples,1000))

    def test_probe_cannot_admit_saturated_or_busy_host(self):
        for busy in (6.1,14):
            samples=[dict(processors=14,capacity=14,busy=busy) for _ in range(8)]
            self.assertIsNone(readiness(samples,1000))
