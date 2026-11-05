import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import analyze_phase10 as analysis
import replay_phase10 as replay


class Phase10EvidenceTests(unittest.TestCase):
    def request(self):
        return dict(load_workers=2,profiled=False,argv=['-v','error'],
                    **{k:'/task/'+k for k in ('binary','output','load_binary','load_prefix','child_report')})

    def test_child_load_budget_rejects_unbounded_and_boolean_counts(self):
        for value in (-1,1,3,100,True,'2'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                replay.validate_child_request(dict(self.request(),load_workers=value))
        replay.validate_child_request(self.request())
        replay.validate_child_request(dict(self.request(),load_workers=0))

    def test_observer_needs_explicit_state_and_absolute_paths(self):
        for request in (dict(self.request(),profiled=1),dict(self.request(),binary='relative'),
                        dict(self.request(),profiled=True,observer='/task/probe',trace='relative')):
            with self.assertRaises(ValueError):replay.validate_child_request(request)

    def test_host_tick_order_and_mach_units(self):
        child=dict(encoding_wall_seconds=2,host_cpu_ticks=[800,200,1700,100],host_clock_ticks=100,
                   load_workers=[dict(rusage_v6=True,duty=50,iterations=1,window_cpu_mach=24000000,mach_numer=125,mach_denom=3)])
        value=analysis.load_window(child,dict(user_seconds=2.5,sys_seconds=.5))
        self.assertEqual(value['host_capacity_cores'],14)
        self.assertEqual(value['host_busy_cores'],5.5)
        self.assertEqual(value['synthetic_cpu_cores'],.5)
        self.assertEqual(value['residual_busy_cores_estimate'],3.5)

    def test_warmup_and_other_controls_cannot_inflate_candidate_gain(self):
        rows=[dict(warmup=False,block=b,label=l,seconds=9 if l=='candidate' else 10)
              for b in range(3) for l in ('original','candidate','stock','stock','candidate','original')]
        rows.append(dict(warmup=True,block=-1,label='candidate',seconds=10000))
        value=analysis.compare(rows,'stock',draws=200)
        self.assertEqual(value['native_stock_ratio'],.9)
        self.assertEqual(value['n_per_engine'],6)
        self.assertTrue(value['improvement_accepted'])

    def test_incomplete_whole_block_cannot_be_promoted(self):
        rows=[dict(warmup=False,block=b,label=l,seconds=10)
              for b in range(3) for l in ('candidate','stock','stock','candidate')]
        rows.pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):analysis.compare(rows,'stock',draws=200)

    def test_missing_entire_predeclared_block_cannot_be_hidden(self):
        rows=[dict(warmup=False,block=b,label=l,seconds=10)
              for b in range(2) for l in ('candidate','stock','stock','candidate')]
        with self.assertRaisesRegex(ValueError,'Predeclared'):analysis.validate_blocks(rows,3,('candidate','stock'))
        analysis.validate_blocks(rows,2,('candidate','stock'))
