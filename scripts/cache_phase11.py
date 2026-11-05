"""One bounded, read-only cache lease across all engines and comparison blocks."""
from __future__ import annotations
import ctypes as C
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import signal
import threading
import time
import uuid

from ffv2.darwin import libraries,process_info
from ffv2.resources import Policy,snapshot,process_memory
from admission_phase11 import wait_window

MINCORE_INCORE=0x01
MINCORE_PAGED_OUT=0x20


class HeldCache:
    def __init__(self,inputs,images,directory,*,settle_seconds=3):
        self.inputs=sorted({str(Path(p).resolve(strict=True)) for p in inputs})
        self.images=sorted(set(images)-set(self.inputs));self.directory=directory
        self.policy=Policy();self.baseline=snapshot(directory);self.entries=[];self.settle_seconds=settle_seconds;self.closed=False
        self.stop=threading.Event();self.thread=None;self.watch_error=None;self.closing=False;self.previous_signal=None
        self.peak_accounted_bytes=0
        self.system,_=libraries();self.page=os.sysconf('SC_PAGESIZE')
        for name,args,result in (
            ('mmap',[C.c_void_p,C.c_size_t,C.c_int,C.c_int,C.c_int,C.c_int64],C.c_void_p),
            ('mlock',[C.c_void_p,C.c_size_t],C.c_int),('munlock',[C.c_void_p,C.c_size_t],C.c_int),
            ('munmap',[C.c_void_p,C.c_size_t],C.c_int),('mincore',[C.c_void_p,C.c_size_t,C.c_void_p],C.c_int)):
            function=getattr(self.system,name);function.argtypes=args;function.restype=result
        self.record={'status':'not_opened','lease_id':uuid.uuid4().hex,'owner_pid':os.getpid(),'sources':self.inputs,
            'images':self.images,'source_limit_bytes':3*1024**3,'image_limit_bytes':256*1024**2,
            'resources_before':self.baseline.json(),'system_memory_checks_ignored':self.policy.ignore_system_memory}

    def resident(self,entry):
        count=(entry['bytes']+self.page-1)//self.page;vector=(C.c_ubyte*count)()
        if self.system.mincore(entry['mapping'],entry['bytes'],vector):raise OSError(C.get_errno(),'mincore')
        return sum(bool(v&MINCORE_INCORE) and not bool(v&MINCORE_PAGED_OUT) for v in vector),count

    def check(self):
        memory,method=process_memory(os.getpid())
        reserve=sum(e.get('bytes',0) for e in self.entries if e['mapping'] is not None)
        accounted=memory+reserve;self.peak_accounted_bytes=max(self.peak_accounted_bytes,accounted)
        reasons=self.policy.running(snapshot(self.directory),self.baseline,accounted)
        if method=='unavailable':reasons.append('job_memory_measurement_unavailable')
        if reasons:raise RuntimeError('Cache lease resources: '+str(reasons))

    def ready(self):
        sample=snapshot(self.directory);reasons=self.policy.admission(sample,8*1024**3,8*1024**3)
        reserve=sum(Path(p).stat().st_size for p in self.inputs+self.images)+2*1024**3
        if self.policy.boot_used_limit is not None and sample.boot_used_bytes+reserve>=self.policy.boot_used_limit:reasons.append('boot_disk_cache_reserve')
        return {'ready':not reasons,'reasons':reasons,'boot_used_bytes':sample.boot_used_bytes,'reserved_bytes':reserve}

    def watch(self):
        while not self.stop.wait(.5):
            try:self.check()
            except BaseException as error:
                self.watch_error=str(error)
                if not self.closing:os.kill(os.getpid(),signal.SIGUSR1)
                return

    def interrupted(self,signum,frame):
        if self.watch_error and not self.closing:raise RuntimeError(self.watch_error)

    def open(self):
        if self.record['status']!='not_opened':raise RuntimeError('Cache lease already used')
        self.baseline=snapshot(self.directory);self.record['resources_before']=self.baseline.json()
        reasons=self.ready()['reasons']
        if reasons:raise RuntimeError('Cache lease admission: '+str(reasons))
        if not self.inputs or len(self.images)>128:raise ValueError('Bounded primary sources and images required')
        totals={'source':0,'image':0};started=time.monotonic()
        try:
            for kind,paths in (('source',self.inputs),('image',self.images)):
                for path in paths:
                    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
                    entry={'fd':fd,'path':path,'kind':kind,'mapping':None,'locked':False};self.entries.append(entry)
                    value=os.fstat(fd)
                    if not stat.S_ISREG(value.st_mode) or value.st_size<1:raise ValueError('Regular nonempty cache image required')
                    totals[kind]+=value.st_size
                    if totals[kind]>(3*1024**3 if kind=='source' else 256*1024**2):raise ValueError('Cache lease size bound')
                    entry.update(bytes=value.st_size,identity=(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns))
                    mapping=self.system.mmap(None,value.st_size,1,1 if kind=='source' else 2,fd,0)
                    if mapping==C.c_void_p(-1).value or mapping is None:raise OSError(C.get_errno(),'mmap')
                    entry['mapping']=mapping
                    if self.system.mlock(mapping,value.st_size):raise OSError(C.get_errno(),'mlock')
                    entry['locked']=True;resident,pages=self.resident(entry)
                    if resident!=pages:raise RuntimeError('Incomplete held cache residency')
                    entry.update(resident_before=resident,pages=pages);self.check()
            time.sleep(self.settle_seconds);self.check()
            self.record.update(status='active',source_bytes=totals['source'],image_bytes=totals['image'],
                conditioning_seconds=time.monotonic()-started,opened_monotonic=time.monotonic(),
                owner_after_lock=process_info(os.getpid()),resources_after_lock=snapshot(self.directory).json())
            self.previous_signal=signal.signal(signal.SIGUSR1,self.interrupted)
            self.thread=threading.Thread(target=self.watch,daemon=True,name='cache-resource-guard');self.thread.start()
            return dict(self.record)
        except BaseException:
            self.close(completed=False);raise

    def close(self,*,completed):
        if self.closed:return dict(self.record)
        self.closing=True;self.stop.set()
        if self.thread:self.thread.join(timeout=2)
        if self.previous_signal is not None:signal.signal(signal.SIGUSR1,self.previous_signal)
        valid=not self.watch_error;proof=[]
        for entry in self.entries:
            try:
                if entry['mapping'] is not None and entry['locked']:
                    resident,pages=self.resident(entry);value=os.fstat(entry['fd'])
                    same=(value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns)==entry['identity']
                    valid=valid and same and resident==pages
                    proof.append({'path':entry['path'],'kind':entry['kind'],'bytes':entry['bytes'],
                        'pages':pages,'resident_before':entry['resident_before'],'resident_after':resident,'unchanged':same})
            except (OSError,ValueError):valid=False
            finally:
                if entry['locked']:self.system.munlock(entry['mapping'],entry['bytes'])
                if entry['mapping'] is not None:self.system.munmap(entry['mapping'],entry['bytes'])
                os.close(entry['fd'])
        self.entries=[];self.closed=True
        self.record.update(status='completed' if completed and valid else 'interrupted',unbroken=valid,
            proof=proof,closed_monotonic=time.monotonic(),owner_after_unlock=process_info(os.getpid()),
            peak_accounted_bytes=self.peak_accounted_bytes,resource_error=self.watch_error,
            watchdog_interval_seconds=.5,memory_accounting='Owned process-tree footprint plus all held mapped file bytes; conservative double counting retained.')
        return dict(self.record)


class ComparisonCaches:
    def __init__(self,sources,images,directory,report,save):
        self.sources=sources;self.images=images;self.directory=directory;self.report=report;self.save=save;self.current=None
        report['cache_holds']={}
        report['cache_scope']='One input and common engine images held throughout each paired block; no pinned input during admission waits.'

    @contextmanager
    def hold(self,profile,load,block,attempt,*,warmup):
        if self.current is not None:raise RuntimeError('Overlapping comparison cache leases')
        held=HeldCache([self.sources[profile]],self.images,self.directory);self.current=held;completed=False
        try:
            remaining=3600-sum(a['wait_seconds'] for a in self.report['admissions'])
            if remaining<1:raise RuntimeError('Automatic CPU/disk admission budget exhausted')
            admission=wait_window(self.directory/'admission.jsonl',f'{profile}-load{load}-block{block}-attempt{attempt}',
                timeout=remaining,required=1 if warmup else 8,probe_after=0 if warmup else 15,admit=held.ready)
            self.report['admissions'].append(dict(admission,profile=profile,load=load,block=block,attempt=attempt,warmup=warmup));self.save()
            self.report['cache_holds'][held.record['lease_id']]=held.open();self.save()
            yield held
            completed=True
        finally:
            proof=held.close(completed=completed);self.report['cache_holds'][held.record['lease_id']]=proof;self.current=None;self.save()
            if completed and proof['status']!='completed':raise RuntimeError('Comparison cache integrity failed')
