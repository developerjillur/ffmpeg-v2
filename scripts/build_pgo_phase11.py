#!/usr/bin/python3 -B
"""Train and build a private M4 codec on disjoint media ranges, without LTO."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from phase11_common import ROOT,WORK,read,guarded
from ffv2.config import check_mounts
from ffv2.engine import selection,library_closure
from ffv2.io import sha256_file,write_json
from verify_phase2 import Verification

SOURCE=Path(str(lab_path('ffmpeg-v2-phase10/x264-row-source')))


def text_command(argv):return subprocess.check_output(argv,text=True,stderr=subprocess.STDOUT).strip()


def stage(label,dependency,proof,source_commit,selected):
    original=Path(selected['install_prefix'])
    identity=sha256_file(dependency/'lib/libx264.165.dylib')[:12]
    prefix=Path(str(lab_path('ffmpeg-v2-core/candidates')))/('phase11-'+label+'-'+identity)/'attempt-001/install'
    check_mounts(prefix)
    if prefix.exists():raise RuntimeError('Preserve existing staged candidate')
    prefix.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    print(json.dumps({'new_native_prefix':str(prefix),'source_install':str(original),'private_dependency':str(dependency)}),flush=True)
    subprocess.run(['/bin/cp','-cRp',str(original),str(prefix)],check=True)
    for relative in ('lib/libx264.165.dylib','lib/libx264.a','include/x264.h','include/x264_config.h','lib/pkgconfig/x264.pc'):
        target=prefix/relative
        if target.exists():raise RuntimeError('Unexpected dependency collision')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dependency/relative,target)
    (prefix/'lib/libx264.dylib').symlink_to('libx264.165.dylib')
    for pc in (prefix/'lib/pkgconfig').glob('*.pc'):pc.write_text(pc.read_text().replace(str(original),str(prefix)).replace(str(dependency),str(prefix)))
    files=[*(prefix/'bin').glob('*'),*(p for p in (prefix/'lib').glob('*.dylib') if not p.is_symlink())]
    print(json.dumps({'owned_macho_changes':[str(f) for f in files]}),flush=True)
    for path in files:
        for line in text_command(['/usr/bin/otool','-L',str(path)]).splitlines()[1:]:
            old=line.strip().split(' (',1)[0]
            if not old.startswith('/'):raise RuntimeError('Absolute library binding required')
            new=old.replace(str(original),str(prefix))
            if Path(old).name=='libx264.165.dylib':new=str(prefix/'lib/libx264.165.dylib')
            if old!=new:subprocess.run(['/usr/bin/install_name_tool','-change',old,new,str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        if path.suffix=='.dylib':subprocess.run(['/usr/bin/install_name_tool','-id',str(path),str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    for path in files:subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(path)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    binaries={name:str(prefix/'bin'/name) for name in ('ffmpeg','ffprobe','ffplay')}
    closure=library_closure([Path(v) for v in binaries.values()]);private=str(prefix/'lib/libx264.165.dylib')
    if [name for name in closure if 'libx264' in Path(name).name]!=[private]:raise RuntimeError('Private codec binding failed')
    result={'status':'training_only' if label=='train' else 'staged_not_activated','label':label,'prefix':str(prefix),
        'binaries':binaries,'files':closure,'source_commit':source_commit,'build_proof':str(proof),
        'profile_instrumented':label=='train','lto':False,'runtime_library_sha256':sha256_file(Path(private))}
    write_json(prefix.parent/'stage.json',result);return result


def main():
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    top=WORK/'pgo'
    if top.exists():raise RuntimeError('Preserve existing profile/build results')
    top.mkdir(mode=0o700);selected=selection(verify_hashes=True)
    initial=read(WORK/'initial.json')
    if selected['selection_id']!=initial['selection']['selection_id']:raise RuntimeError('Frozen baseline changed')
    source_commit=text_command(['/usr/bin/git','-C',str(SOURCE),'rev-parse','HEAD'])
    source_tree=text_command(['/usr/bin/git','-C',str(SOURCE),'rev-parse','HEAD^{tree}'])
    lock=read(ROOT/'third_party/x264/manifest.json')
    if source_tree!=lock['patched_tree'] or text_command(['/usr/bin/git','-C',str(SOURCE),'status','--porcelain']):raise RuntimeError('Clean pinned codec source required')
    verify=Verification(Path(selected['install_prefix']),top/'guarded')
    report={'status':'running','source_commit':source_commit,'source_tree':source_tree,'compiler':text_command(['/usr/bin/clang','--version']),
        'steps':[],'builds':{},'training':[],'scope':'Source f70c7f8, M4 vectorization, profile-guided code generation without LTO. Training ranges exclude BBB 60–120/60–90 confirmation. No codec safety checks disabled.'}
    target=top/'report.json';write_json(target,report)
    def step(name,argv,output,timeout=600,budget=256*1024**2):
        receipt,path=guarded(verify,name,argv,output,timeout=timeout,budget=budget)
        report['steps'].append({'name':name,'path':str(path),'sha256':sha256_file(path),'exit_code':receipt['exit_code']});write_json(target,report)
        return receipt
    def build(label,profile_flags,link_flags=''):
        directory=top/label;build=directory/'build';prefix=directory/'install'
        build.mkdir(parents=True,mode=0o700);(prefix/'lib').mkdir(parents=True,mode=0o700)
        options=[str(SOURCE/'configure'),'--prefix='+str(prefix),'--disable-lsmash','--disable-swscale','--disable-ffms',
            '--enable-shared','--enable-static','--enable-strip','--disable-cli','--extra-cflags=-mcpu=apple-m4 '+profile_flags,
            '--extra-asflags=-mcpu=apple-m4','--extra-ldflags='+link_flags]
        step(label+'-configure',[sys.executable,'-B','-c','import os,sys;os.environ["CC"]="/usr/bin/clang";os.chdir(sys.argv[1]);os.execv(sys.argv[2],sys.argv[2:])',str(build),*options],build,timeout=120)
        config=build/'config.mak';value=config.read_text()
        if '-DNDEBUG' in value or '-flto' in value:raise RuntimeError('Unexpected disabled checks or LTO')
        if '-fno-tree-vectorize' not in value:raise RuntimeError('Unexpected baseline compiler flags')
        value=value.replace('-fno-tree-vectorize','-fvectorize -fslp-vectorize')
        if label=='use':value=value.replace('CFLAGS=','CFLAGS=-Werror=profile-instr-out-of-date ',1)
        print(json.dumps({'owned_build_configuration':str(config),'profile':label}),flush=True);config.write_text(value)
        step(label+'-compile',['/usr/bin/make','-C',str(build),'-j2','lib-shared','lib-static'],build)
        step(label+'-install',['/usr/bin/make','-C',str(build),'install-lib-shared','install-lib-static'],prefix)
        report['builds'][label]={'prefix':str(prefix),'config_sha256':sha256_file(config),'library_sha256':sha256_file(prefix/'lib/libx264.165.dylib')}
        write_json(target,report);return prefix
    try:
        profile_dir=top/'raw-profiles';profile_dir.mkdir(mode=0o700)
        generated=build('generate','-fprofile-instr-generate='+str(profile_dir/'configure-%m-%p.profraw')+' -fprofile-update=atomic','-fprofile-instr-generate')
        training=stage('train',generated,target,source_commit,selected);write_json(top/'training-stage.json',training)
        profiles=read(Path(str(lab_path('ffmpeg-v2-phase8/confirm-20261103T181013-bc270fb1/report.json'))))['profiles']
        binary=training['binaries']['ffmpeg']
        cases=[('bbb-20-25',profiles['bbb-1080'],20,5,30),('tos-30-35',profiles['tos-liveaction'],30,5,24)]
        for label,source,start,duration,fps in cases:
            if sha256_file(Path(source['input']))!=source['source_sha256']:raise RuntimeError('Training source changed')
            output=top/(label+'.mp4');pattern=profile_dir/(label+'-%m-%p.profraw')
            argv=['/usr/bin/env','LLVM_PROFILE_FILE='+str(pattern),binary,'-v','error','-nostdin','-n','-xerror','-nostats','-progress','pipe:1',
                '-filter_threads','2','-threads','2','-ss',str(start),'-i',source['input'],'-t',str(duration),'-frames:v',str(duration*fps),
                '-an','-c:v','libx264','-preset','veryfast','-crf','20','-threads:v','8','-pix_fmt','yuv420p','-r',str(fps),'-fps_mode','cfr',str(output)]
            receipt=step('train-'+label,argv,output,timeout=1200)
            if int(receipt['last_progress']['frame'])!=duration*fps:raise RuntimeError('Training frame count failed')
            report['training'].append({'label':label,'input':source['input'],'source_sha256':source['source_sha256'],'start':start,'duration':duration,'frames':duration*fps,'output_sha256':sha256_file(output)})
            write_json(target,report)
        output=top/'ten-bit.mp4'
        receipt=step('train-ten-bit',['/usr/bin/env','LLVM_PROFILE_FILE='+str(profile_dir/'ten-bit-%m-%p.profraw'),binary,'-v','error','-nostdin','-n','-xerror',
            '-nostats','-progress','pipe:1','-filter_threads','1','-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=2',
            '-frames:v','60','-vf','format=yuv420p10le','-an','-c:v','libx264','-preset','veryfast','-crf','20','-threads:v','4',str(output)],output,timeout=600)
        if int(receipt['last_progress']['frame'])!=60:raise RuntimeError('10-bit training count failed')
        report['training'].append({'label':'ten-bit','source':'generated testsrc2 640x360/30','frames':60,'output_sha256':sha256_file(output)})
        files=sorted([*profile_dir.glob('bbb-*.profraw'),*profile_dir.glob('tos-*.profraw'),*profile_dir.glob('ten-bit-*.profraw')])
        if len(files)<3 or len(files)>12:raise RuntimeError('Bounded complete training profiles required')
        report['raw_profiles']=[{'path':str(p),'sha256':sha256_file(p),'bytes':p.stat().st_size} for p in files]
        profdata=top/'codec.profdata';profiler='/Library/Developer/CommandLineTools/usr/bin/llvm-profdata'
        print(json.dumps({'merge_profiles':[str(p) for p in files],'new_profile':str(profdata)}),flush=True)
        step('merge-profile',[profiler,'merge','-o',str(profdata),*[str(p) for p in files]],profdata)
        report['profile_summary']=text_command([profiler,'show',str(profdata)])[:6000];report['profile_sha256']=sha256_file(profdata)
        used=build('use','-fprofile-instr-use='+str(profdata))
        candidate=stage('pgo',used,target,source_commit,selected)
        symbols=text_command(['/usr/bin/nm','-g',str(Path(candidate['prefix'])/'lib/libx264.165.dylib')])
        if '__llvm_profile' in symbols or '__llvm_prf' in symbols:raise RuntimeError('Training instrumentation leaked into final candidate')
        candidate.update(profile_data=str(profdata),profile_sha256=report['profile_sha256'])
        write_json(top/'candidate.json',candidate);report['candidate']=str(top/'candidate.json')
        if text_command(['/usr/bin/git','-C',str(SOURCE),'rev-parse','HEAD'])!=source_commit:raise RuntimeError('Codec source changed')
        report['status']='completed';write_json(target,report)
    except BaseException as error:report.update(status='failed',error=str(error)[:4000]);write_json(target,report);raise
    print(json.dumps({'report':str(target),'candidate':report['candidate']}))


if __name__=='__main__':main()
