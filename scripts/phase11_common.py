"""Task-local guarded execution and immutable Phase 11 inputs."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
from pathlib import Path
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
WORK=Path(str(lab_path('ffmpeg-v2-phase11')))
sys.path.insert(0,str(ROOT))
from ffv2.io import digest,write_json,sha256_file
from ffv2.resources import snapshot
from ffv2.worker import host_lock,supervised


def read(path):return json.loads(Path(path).read_text())


def freeze_sources(directory,names):
    result={}
    for name in names:
        source=ROOT/'scripts'/name;destination=directory/(name+'.frozen');data=source.read_bytes()
        if len(data)>1024**2:raise RuntimeError('Bounded measurement source required')
        with destination.open('xb') as stream:stream.write(data)
        if sha256_file(source)!=sha256_file(destination):raise RuntimeError('Measurement source changed during freeze')
        result[name]={'path':str(destination),'sha256':sha256_file(destination)}
    return result


def guarded(verify,name,argv,output,*,memory=4*1024**3,budget=256*1024**2,timeout=1200):
    diagnostic=verify.directory/(name+'-'+uuid.uuid4().hex[:8]+'.diagnostic.json')
    plan={'kind':'diagnostic','spec':{'operation':name,'output':str(diagnostic)},
          'estimates':{'job_memory_bytes':memory,'output_budget_bytes':budget},'timeout_seconds':timeout}
    plan['plan_id']=digest(plan);queued=verify.store.enqueue(plan);job=verify.store.claim(queued['id'])
    attempt=verify.store.root/'jobs'/job['id']/'attempt-001';attempt.mkdir(parents=True)
    try:
        with host_lock(verify.settings) as lock_fd:
            receipt=supervised(argv,name,job,attempt,verify.settings,snapshot(verify.directory),lock_fd,output)
        verify.store.update(job['id'],'completed',receipt=receipt);write_json(diagnostic,receipt)
        return receipt,diagnostic
    except BaseException:
        verify.store.update(job['id'],'failed');raise
