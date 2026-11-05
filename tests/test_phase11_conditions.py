import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import conditions_phase11 as conditions


class ConditionedReplayTests(unittest.TestCase):
    def data(self,load=0):
        per_second=24_000_000;synthetic=.8 if load else 0
        busy=int((6+synthetic)*100)
        return {'status':'completed','mach_numer':125,'mach_denom':3,'clock_ticks':100,'logical_cpus':14,
            'pages':100,'resident_before':100,'resident_after':100,'source_unchanged':True,
            'cache_locked':True,'images_locked':True,'cpu_backend':'host_processor_info','max_background_cores':14.5,
            'pre_background_cores':4,
            'process':{'wall_seconds':2,'user_mach':4*per_second,'system_mach':0,'child_user_raw':0,'child_system_raw':0,
                'wait4_cpu_seconds':4,'instructions':1000,'p_instructions':900,'disk_read_bytes':0},
            'samples':[{'seconds':t,'ticks':[t*busy,0,t*(1400-busy),0],
                        'cpu_mach':t*2*per_second,'child_cpu_raw':0,'load_cpu_mach':int(t*synthetic*per_second),
                        'monitor_cpu_mach':0} for t in (0,1,2)]}

    def test_mach_units_and_external_cpu_are_calibrated(self):
        for load in (0,2):
            result=conditions.validate_case(self.data(load),load)
            self.assertTrue(result['valid'],result['reasons'])
            self.assertAlmostEqual(result['background_cores'],4)
            self.assertAlmostEqual(result['cpu_capacity_cores'],14)

    def test_resident_input_and_locked_images_are_required(self):
        for key,value in (('resident_after',99),('cache_locked',False),('images_locked',False)):
            data=self.data();data[key]=value
            self.assertFalse(conditions.validate_case(data,0)['valid'])

    def test_cached_counter_backend_cannot_be_promoted(self):
        data=self.data();data['cpu_backend']='host_statistics'
        self.assertIn('cpu_counter_backend',conditions.validate_case(data,0)['reasons'])

    def test_counter_plateau_is_rejected_even_with_forged_backend(self):
        data=self.data()
        for row in data['samples']:row['ticks']=[0,0,0,0]
        self.assertIn('cpu_counter_capacity',conditions.validate_case(data,0)['reasons'])

    def test_physical_reads_and_capture_delay_are_environment_failures(self):
        data=self.data();data['process']['disk_read_bytes']=9*1024**2
        self.assertIn('physical_read_budget',conditions.validate_case(data,0)['reasons'])
        data=self.data();data['process']['wall_seconds']=1.9
        self.assertIn('counter_capture_delay',conditions.validate_case(data,0)['reasons'])

    def rows(self):
        environment=conditions.validate_case(self.data(),0)
        return [{'label':label,'seconds':10,'environment':copy.deepcopy(environment)}
                for label in ('original','candidate','stock','stock','candidate','original')]

    def test_slow_timings_are_never_an_exclusion_rule(self):
        rows=self.rows()
        for row in rows:
            if row['label']=='candidate':row['seconds']=10000
        self.assertTrue(conditions.validate_block(rows,('original','candidate','stock'),0)['valid'])

    def test_entire_unstable_block_is_rejected(self):
        rows=self.rows();rows[1]['environment']['background_cores']+=1
        result=conditions.validate_block(rows,('original','candidate','stock'),0)
        self.assertFalse(result['valid']);self.assertIn('background_cores_block_span',result['reasons'])
        rows=self.rows();rows[1]['environment']['p_instruction_fraction']+=.04
        self.assertFalse(conditions.validate_block(rows,('original','candidate','stock'),0)['valid'])

    def test_missing_control_and_disabled_admission_cannot_pass(self):
        self.assertFalse(conditions.validate_block(self.rows()[:-1],('original','candidate','stock'),0)['valid'])
        data=self.data();data['max_background_cores']=-1
        self.assertIn('cpu_admission_policy_mismatch',conditions.validate_case(data,0)['reasons'])

    def test_saturated_host_requires_matched_delivered_cpu(self):
        rows=self.rows();rows[1]['environment']['delivered_cpu_cores']*=1.15
        self.assertIn('delivered_cpu_relative_block_span',conditions.validate_block(rows,('original','candidate','stock'),0)['reasons'])
