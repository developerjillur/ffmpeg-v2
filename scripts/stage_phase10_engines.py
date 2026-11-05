#!/usr/bin/python3 -B
"""Stage private x264 controls beside immutable native installs; never activate."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.config import check_mounts
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json


def command(argv):return subprocess.check_output(argv,text=True,stderr=subprocess.STDOUT)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',choices=('base','opt','m4','m4safe','row','rowvec','check'),action='append');args=parser.parse_args()
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    work=Path(str(lab_path('ffmpeg-v2-phase10')))
    selected=selection(verify_hashes=True);original=Path(selected['install_prefix'])
    records=json.loads((work/'staged-engines.json').read_text()) if (work/'staged-engines.json').exists() else {}
    for label in args.label or ('base','opt'):
        proof=json.loads((work/('x264-build-proof-'+label)/'build.json').read_text())
        if proof['status']!='completed':raise RuntimeError('Private dependency build incomplete')
        identity=proof['source'][:7]
        prefix=Path(str(lab_path('ffmpeg-v2-core/candidates')))/('phase10-'+label+'-'+identity)/'attempt-001/install'
        check_mounts(prefix);prefix.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if prefix.exists():raise RuntimeError('Preserve existing staged prefix')
        print(json.dumps({'copy_from':str(original),'new_prefix':str(prefix),'dependency':proof['prefix']}),flush=True)
        subprocess.run(['/bin/cp','-cRp',str(original),str(prefix)],check=True)
        dependency=Path(proof['prefix'])
        for relative in ('lib/libx264.165.dylib','lib/libx264.a','include/x264.h','include/x264_config.h','lib/pkgconfig/x264.pc'):
            target=prefix/relative
            if target.exists():raise RuntimeError('Unexpected existing private dependency')
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dependency/relative,target)
        (prefix/'lib/libx264.dylib').symlink_to('libx264.165.dylib')
        for pc in (prefix/'lib/pkgconfig').glob('*.pc'):
            pc.write_text(pc.read_text().replace(str(original),str(prefix)).replace(str(dependency),str(prefix)))
        files=[*(prefix/'bin').glob('*'),*(p for p in (prefix/'lib').glob('*.dylib') if not p.is_symlink())]
        print(json.dumps({'owned_macho_changes':[str(p) for p in files]}),flush=True)
        for path in files:
            if path.is_symlink() or not path.is_file():continue
            linked=command(['/usr/bin/otool','-L',str(path)])
            for line in linked.splitlines()[1:]:
                old=line.strip().split(' (',1)[0]
                if not old.startswith('/'):raise RuntimeError('Absolute dependency binding required')
                replacement=old.replace(str(original),str(prefix))
                if Path(old).name=='libx264.165.dylib':replacement=str(prefix/'lib/libx264.165.dylib')
                if old!=replacement:
                    subprocess.run(['/usr/bin/install_name_tool','-change',old,replacement,str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if path.suffix=='.dylib':
                subprocess.run(['/usr/bin/install_name_tool','-id',str(path),str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        for path in files:
            subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        binaries={name:str(prefix/'bin'/name) for name in ('ffmpeg','ffprobe','ffplay')}
        closure=library_closure([Path(value) for value in binaries.values()])
        private=prefix/'lib/libx264.165.dylib'
        if str(private) not in closure or any('x264' in name and name!=str(private) for name in closure):
            raise RuntimeError('Private encoder binding failed')
        record={'status':'staged_not_activated','label':label,'prefix':str(prefix),'binaries':binaries,
                'files':closure,'original_selection_id':selected['selection_id'],'x264_build':str(work/('x264-build-proof-'+label)/'build.json'),
                'source_commit':command(['/usr/bin/git','-C',str(work/('x264-source' if label=='base' else 'x264-check-source' if label=='check' else 'x264-row-source' if label.startswith('row') else 'x264-opt-source')),'rev-parse','HEAD']).strip(),
                'ffmpeg_version':command([binaries['ffmpeg'],'-version']).splitlines()[0],
                'runtime_library_sha256':sha256_file(private)}
        write_json(prefix.parent/'stage.json',record);records[label]=record
        print(json.dumps({'label':label,'prefix':str(prefix),'files':len(closure)}),flush=True)
    selection(verify_hashes=True)
    write_json(work/'staged-engines.json',records)


if __name__=='__main__':main()
