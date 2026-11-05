import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from conditions_phase11 import DEFAULT_POLICY
from watch_phase11 import retryable,same_content_closure


class UnmeasuredRecoveryTests(unittest.TestCase):
    def timeout(self):
        return {'phase':11,'mode':'confirm','status':'failed','error':'Automatic stable-window admission budget exhausted',
            'rows':[{'warmup':True,'seconds':3}], 'blocks':[],'required_valid_blocks':9,
            'environment_policy':copy.deepcopy(DEFAULT_POLICY),'specifications':{'hd60':{},'raw30':{}},
            'load_levels':[0,2],'cache_holds':{'a':{'status':'interrupted'}}}

    def test_pure_wait_timeout_can_restart_without_importing_warmup(self):
        self.assertTrue(retryable(self.timeout()))

    def test_started_measured_case_or_attempt_cannot_reset_trial(self):
        for update in ({'rows':[{'warmup':False}]},{'blocks':[{'validation':{'valid':False}}]}):
            value=self.timeout();value.update(update);self.assertFalse(retryable(value))

    def test_resource_failure_changed_policy_and_live_cache_cannot_retry(self):
        for update in ({'error':'boot_disk_400gb_limit'},{'environment_policy':{}},
                       {'cache_holds':{'a':{'status':'active'}}},{'status':'completed'},{'required_valid_blocks':3}):
            value=self.timeout();value.update(update);self.assertFalse(retryable(value))

    def test_mount_recovery_allows_only_device_number_difference(self):
        before={'/native/lib':{'identity':{'device':1,'inode':2,'size':3,'mtime_ns':4},'sha256':'same','load_paths':['/native/lib']}}
        after=copy.deepcopy(before);after['/native/lib']['identity']['device']=5
        self.assertTrue(same_content_closure(before,after))
        for part,value in (('sha256','different'),('load_paths',['/another/lib'])):
            changed=copy.deepcopy(after);changed['/native/lib'][part]=value;self.assertFalse(same_content_closure(before,changed))
        changed=copy.deepcopy(after);changed['/native/lib']['identity']['inode']=99;self.assertFalse(same_content_closure(before,changed))
