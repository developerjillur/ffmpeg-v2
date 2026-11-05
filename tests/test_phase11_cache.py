import sys as _path_sys
from pathlib import Path as _Path
_path_sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / "scripts"))
from public_paths import lab_path, project_path
import ctypes as C
import errno
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cache_phase11 import HeldCache
from ffv2.config import check_mounts
from ffv2.resources import Snapshot


@unittest.skipUnless(sys.platform=='darwin','Darwin cache lease')
class HeldCacheTests(unittest.TestCase):
    def setUp(self):
        self.directory=Path(str(lab_path('ffmpeg-v2-phase11/cache-unit-fixtures')))/uuid.uuid4().hex
        check_mounts(self.directory)
        self.directory.mkdir(parents=True)
        self.source=self.directory/'source';self.image=self.directory/'image'
        self.source.write_bytes(b'source'*4096);self.image.write_bytes(b'image'*4096)
        self.resource=patch('cache_phase11.snapshot',return_value=Snapshot('normal',32*1024**3,0,100*1024**3,100*1024**3,100*1024**3))
        self.memory=patch('cache_phase11.process_memory',return_value=(0,'fixture'))
        self.resource.start();self.memory.start();self.addCleanup(self.resource.stop);self.addCleanup(self.memory.stop)

    def cache(self):return HeldCache([self.source],[str(self.image)],self.directory,settle_seconds=0)

    def test_readonly_lease_covers_full_comparison_and_releases(self):
        before=self.source.read_bytes();held=self.cache()
        try:
            opened=held.open();self.assertEqual(opened['status'],'active');held.check()
        finally:closed=held.close(completed=True)
        self.assertEqual(closed['status'],'completed');self.assertTrue(closed['unbroken'])
        self.assertEqual(len(closed['proof']),2);self.assertEqual(before,self.source.read_bytes())
        self.assertEqual(held.close(completed=True),closed)

    def test_partial_mlock_failure_releases_maps_and_descriptors(self):
        held=self.cache();original=held.system.mlock;seen=[]
        def lock(address,size):
            seen.append((address,size))
            if len(seen)>1:C.set_errno(errno.ENOMEM);return -1
            return original(address,size)
        with patch.object(held.system,'mlock',side_effect=lock),\
                patch.object(held.system,'munlock',wraps=held.system.munlock) as unlock,\
                patch.object(held.system,'munmap',wraps=held.system.munmap) as unmap,self.assertRaises(OSError):held.open()
        self.assertEqual(held.entries,[]);self.assertEqual(held.record['status'],'interrupted')
        self.assertEqual(unlock.call_count,1);self.assertEqual(unmap.call_count,2)
        self.assertEqual({c.args for c in unmap.call_args_list},set(seen))

    def test_oversized_source_is_rejected_before_mapping(self):
        held=self.cache()
        with patch('cache_phase11.os.fstat',return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_size=3*1024**3+1)),\
                patch.object(held.system,'mmap',side_effect=AssertionError('unbounded allocation')),self.assertRaises(ValueError):held.open()
        self.assertEqual(held.entries,[]);self.assertEqual(held.record['status'],'interrupted')

    def test_wired_file_reserve_counts_toward_job_memory_limit(self):
        held=self.cache()
        with patch('cache_phase11.process_memory',return_value=(12*1024**3,'fixture')),self.assertRaisesRegex(RuntimeError,'job_memory_over_12gib'):
            held.open()
        self.assertEqual(held.entries,[])

    def test_darwin_mincore_reference_and_paged_out_bits_are_distinct(self):
        held=self.cache();entry={'bytes':held.page,'mapping':None}
        for flags,expected in ((0x01,1),(0x01|0x08,1),(0x01|0x20,0),(0x20,0)):
            def mincore(address,size,vector):vector[0]=flags;return 0
            with patch.object(held.system,'mincore',side_effect=mincore):self.assertEqual(held.resident(entry),(expected,1))
