from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ffv2.bindings import assert_workflow
from ffv2.checkpoints import configure
from ffv2.config import Settings
from ffv2.errors import FFV2Error
from ffv2.io import digest, fingerprint, sha256_file, write_json
from ffv2.releases import quiescent
from ffv2.store import Store

class CheckpointLifecycleTests(unittest.TestCase):
    def test_checkpoint_refuses_implicit_vfr_and_fractional_frame_ranges(self):
        def plan():
            return {'spec':{'operation':'transcode','fps':30,'checkpoint_seconds':10},
                'source':{'video':{'avg_frame_rate':'30/1','r_frame_rate':'30/1','start_time':'0'},'format':{'start_time':'0'}},
                'expected':{'duration_seconds':12},'estimates':{'output_budget_bytes':1000},'warnings':[]}
        p=plan();configure(p)
        self.assertEqual(p['checkpoint']['segments'],2)
        self.assertEqual(p['expected']['video_frames'],360)
        for change in ('vfr','implicit','grid'):
            p=plan()
            if change=='vfr':p['source']['video']['avg_frame_rate']='20/1'
            if change=='implicit':del p['spec']['fps']
            if change=='grid':p['spec']['start']=.01
            with self.subTest(change=change),self.assertRaises(FFV2Error):configure(p)

    def test_workflow_change_refuses_saved_plan(self):
        with patch('ffv2.bindings.workflow_identity',return_value='new'):
            with self.assertRaises(FFV2Error) as error:assert_workflow({'runtime_code_id':'old'})
        self.assertEqual(error.exception.code,'runtime_code_changed')

    def test_published_recovery_requires_valid_decode_digest_and_inode(self):
        for mode in ('valid','bad-digest','wrong-inode','decode-failed'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as area:
                root=Path(area)
                settings=Settings(state=root/'state',output_roots=(root,),input_roots=(root,),host_lock=root/'host.lock')
                store=Store(settings)
                output=root/'final.mp4'
                plan={'plan_id':'saved-plan','spec':{'operation':'transcode','output':str(output)}}
                queued=store.enqueue(plan);job=store.claim(queued['id'])
                directory=store.root/'jobs'/job['id']/'attempt-001';directory.mkdir(parents=True)
                stage=directory/'stage.mp4';stage.write_bytes(b'task-created validated fixture')
                import os
                if mode=='wrong-inode':output.write_bytes(stage.read_bytes())
                else:os.link(stage,output)
                receipt={'status':'completed','plan_id':plan['plan_id'],'output':str(output),'staging_output':str(stage),
                    'output_sha256':sha256_file(stage),'publish_identity':fingerprint(stage),
                    'validation':{'full_decode':{'status':'failed' if mode=='decode-failed' else 'completed'}}}
                write_json(directory/'publish-intent.json',{'receipt':receipt,'digest':'bad' if mode=='bad-digest' else digest(receipt)})
                store.recover()
                self.assertEqual(store.get(job['id'],plan=False)['status'],'completed' if mode=='valid' else 'interrupted')

    def test_release_update_refuses_queued_jobs_without_changing_them(self):
        with tempfile.TemporaryDirectory() as area:
            root=Path(area)
            settings=Settings(state=root/'state',output_roots=(root,),host_lock=root/'host.lock')
            store=Store(settings)
            job=store.enqueue({'plan_id':'p','spec':{'output':str(root/'output.mp4')}})
            with patch('ffv2.releases.PROJECT',root),self.assertRaises(FFV2Error) as error:quiescent(settings)
            self.assertEqual(error.exception.code,'release_jobs_active')
            self.assertEqual(store.get(job['id'],plan=False)['status'],'queued')

    def test_release_gate_preserves_special_characters_in_state_path(self):
        with tempfile.TemporaryDirectory() as area:
            root=Path(area)
            settings=Settings(state=root/'state ? # বাংলা',output_roots=(root,),host_lock=root/'host.lock')
            store=Store(settings)
            job=store.enqueue({'plan_id':'p','spec':{'output':str(root/'out.mp4')}})
            with patch('ffv2.releases.PROJECT',root),self.assertRaises(FFV2Error) as error:quiescent(settings)
            self.assertEqual(error.exception.code,'release_jobs_active')
            self.assertEqual(store.get(job['id'],plan=False)['status'],'queued')

    def test_stale_release_cannot_enqueue_after_activation(self):
        import os
        with tempfile.TemporaryDirectory() as area:
            root=Path(area);pointer=root/'active-release.json'
            write_json(pointer,{'release_id':'new'})
            settings=Settings(state=root/'state',output_roots=(root,),host_lock=root/'host.lock')
            store=Store(settings)
            with patch('ffv2.releases.ACTIVE',pointer),patch.dict(os.environ,{'FFV2_RELEASE_ID':'old'}),self.assertRaises(FFV2Error) as error:
                store.enqueue({'plan_id':'p','spec':{'output':str(root/'out.mp4')}})
            self.assertEqual(error.exception.code,'release_changed')
            self.assertEqual(store.list(),[])

    def test_activation_fence_blocks_a_stale_concurrent_enqueue(self):
        import os,select,subprocess,sys
        from ffv2.releases import lifecycle_lock
        with tempfile.TemporaryDirectory() as area:
            root=Path(area);(root/'.runtime').mkdir()
            pointer=root/'.runtime/active-release.json';write_json(pointer,{'release_id':'old'})
            settings=Settings(state=root/'state',output_roots=(root,),host_lock=root/'host.lock')
            code="""import json,sys
from pathlib import Path
from ffv2.config import Settings
from ffv2.store import Store
from ffv2.errors import FFV2Error
r=Path(sys.argv[1]);s=Store(Settings(state=r/'state',output_roots=(r,),host_lock=r/'host.lock'))
print('ready',flush=True)
try:s.enqueue({'plan_id':'p','spec':{'output':str(r/'out.mp4')}});print('unexpected queue',flush=True)
except FFV2Error as e:print(e.code,flush=True)
"""
            env={**os.environ,'FFV2_PROJECT_ROOT':str(root),'FFV2_RELEASE_ID':'old'}
            with lifecycle_lock(settings,exclusive=True):
                child=subprocess.Popen([sys.executable,'-B','-c',code,str(root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
                if not select.select([child.stdout],[],[],5)[0]:
                    child.kill();child.communicate();self.fail('Concurrent submit helper did not start')
                self.assertEqual(child.stdout.readline().strip(),'ready')
                write_json(pointer,{'release_id':'new'})
                self.assertIsNone(child.poll())
            try:
                out,err=child.communicate(timeout=5)
                self.assertEqual((child.returncode,out.strip(),err),(0,'release_changed',''))
            finally:
                if child.poll() is None:child.kill();child.communicate()
            self.assertEqual(Store(settings).list(),[])

    def test_preemption_uses_the_same_aging_score_as_claim(self):
        with tempfile.TemporaryDirectory() as area:
            root=Path(area);settings=Settings(state=root/'state',output_roots=(root,))
            store=Store(settings)
            first=store.enqueue({'plan_id':'a','spec':{'output':str(root/'a.mp4'),'priority':0}})
            store.claim(first['id'])
            low=store.enqueue({'plan_id':'b','spec':{'output':str(root/'b.mp4'),'priority':-10}})
            self.assertFalse(store.higher_priority_waiting(first['id']))
            with store.connect() as db:db.execute('UPDATE jobs SET created=created-1000 WHERE id=?',(low['id'],))
            self.assertTrue(store.higher_priority_waiting(first['id']))

    def test_corrupted_database_is_a_typed_mcp_error_and_is_preserved(self):
        from ffv2.mcp import Server
        import json
        with tempfile.TemporaryDirectory() as area:
            root=Path(area);state=root/'state';state.mkdir()
            database=state/'jobs.sqlite3';database.write_bytes(b'controlled corrupt database fixture')
            before=sha256_file(database)
            settings=Settings(state=state,output_roots=(root,))
            server=Server(settings);server.ready=True
            response=server.handle({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'ffv2_job_status','arguments':{'job_id':'a'*32}}})
            self.assertTrue(response['result']['isError'])
            self.assertEqual(json.loads(response['result']['content'][0]['text'])['code'],'state_unavailable')
            self.assertEqual(sha256_file(database),before)

if __name__=='__main__':unittest.main()
