#!/usr/bin/python3 -B
"""Adjacent HD stage pairs isolate producer, x264 and audio/mux scheduling."""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.engine import selection
from ffv2.io import sha256_file,write_json
from ffv2.resources import Policy,snapshot
from verify_phase2 import Verification


def main():
    os.nice(max(0,10-os.getpriority(os.PRIO_PROCESS,0)))
    selected=selection(verify_hashes=True)
    source=Path(str(lab_path('ffmpeg-v2-phase4/corpus/bbb-1080.mp4')))
    directory=Path(str(lab_path('ffmpeg-v2-phase8')))/('isolation-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    reasons=Policy().admission(snapshot(directory),3*1024**3,4*1024**3)
    if reasons:
        raise RuntimeError(str(reasons))
    verify=Verification(Path(selected['install_prefix']),directory)
    raw=directory/'bbb-1080-60-to90.yuv'
    native=selected['binaries']['ffmpeg']
    engines={'native':native,'stock':'/opt/homebrew/bin/ffmpeg'}
    expected=1920*1080*3//2*900
    report={'status':'running','directory':str(directory),'engine_selection_id':selected['selection_id'],
        'source':str(source),'source_sha256':sha256_file(source),'start_seconds':60,'seconds':30,'frames':900,
        'nice':os.getpriority(os.PRIO_PROCESS,0),'initial_resources':snapshot(directory).json(),
        'rows':[],'summary':{},'comparisons':{},'raw':{},
        'scope':'Adjacent alternating pairs; five measured repetitions and one excluded warmup. Diagnostic stages only, not full workflow acceptance or a new quality preset.'}
    path=directory/'isolation.json'
    def save(): write_json(path,report)
    def base(binary):
        return [binary,'-v','error','-nostdin','-n','-xerror','-nostats','-progress','pipe:1',
                '-stats_period','1','-filter_threads','2','-filter_complex_threads','2','-threads','2']
    source_input=['-ss','60','-i',str(source)]
    decode_options=['-frames:v','900','-vf','scale=1920:1080,setsar=1','-pix_fmt','yuv420p']
    try:
        save()
        receipt=verify.aux('raw-reference',base(native)+source_input+decode_options+
            ['-an','-c:v','rawvideo','-threads:v','1','-f','rawvideo',str(raw)],raw,budget=expected+1024**2,timeout=180)
        if raw.stat().st_size!=expected or int(receipt['last_progress']['frame'])!=900:
            raise RuntimeError('Raw reference coverage mismatch')
        checksum=sha256_file(raw)
        stock_hash=directory/'stock-decoded.sha256'
        verify.aux('stock-reference-hash',base(engines['stock'])+source_input+decode_options+
            ['-an','-c:v','rawvideo','-threads:v','1','-f','hash','-hash','sha256',str(stock_hash)],stock_hash,timeout=180)
        if stock_hash.read_text().strip().split('=')[-1].lower()!=checksum:
            raise RuntimeError('Decoded Native/Stock reference pixels differ')
        report['raw']={'path':str(raw),'sha256':checksum,'bytes':expected,'stock_decoded_hash':str(stock_hash),'pixels_identical':True}
        save()
        rng=random.Random(202611048)
        for trial in range(6):
            modes=['decode_filter','raw_x264','direct_video','direct_av'];rng.shuffle(modes)
            for mode in modes:
                labels=['native','stock'] if (trial+modes.index(mode))%2 else ['stock','native']
                for label in labels:
                    identity=mode+'-'+label+'-'+str(trial)
                    output=directory/(identity+('.null' if mode=='decode_filter' else '.mp4'))
                    argv=base(engines[label])
                    argv+=['-f','rawvideo','-pix_fmt','yuv420p','-video_size','1920x1080','-framerate','30','-i',str(raw)] if mode=='raw_x264' else source_input
                    argv+=decode_options
                    if mode=='decode_filter':
                        argv+=['-an','-c:v','rawvideo','-threads:v','1','-f','null','-']
                    else:
                        argv+=['-map','0:v:0','-c:v','libx264','-threads:v','8','-preset','veryfast','-crf','20','-r','30','-fps_mode','cfr']
                        argv+=['-map','0:a:0','-t','30','-c:a','aac','-b:a','160k','-threads:a','1'] if mode=='direct_av' else ['-an']
                        argv+=['-map_metadata','-1','-map_chapters','-1','-movflags','+faststart','-f','mp4',str(output)]
                    receipt=verify.aux(identity,argv,output,budget=64*1024**2,timeout=180)
                    if int(receipt['last_progress']['frame'])!=900:
                        raise RuntimeError('Diagnostic frame coverage mismatch')
                    report['rows'].append({'mode':mode,'label':label,'trial':trial,'warmup':trial==0,
                        'seconds':receipt['wall_seconds'],'peak_job_memory_bytes':receipt['peak_job_memory_bytes'],
                        'output':str(output) if output.exists() else None,
                        'output_sha256':sha256_file(output) if output.exists() else None,
                        'receipt':str(next(directory.glob(identity+'-*.diagnostic.json')))})
                    save()
                    print(json.dumps({'stage':mode,'engine':label,'trial':trial,'seconds':round(receipt['wall_seconds'],3)}),flush=True)
        for mode in ('decode_filter','raw_x264','direct_video','direct_av'):
            groups={label:{r['trial']:r for r in report['rows'] if r['mode']==mode and r['label']==label and not r['warmup']} for label in engines}
            for label,rows in groups.items():
                report['summary'][mode+'/'+label]={'n':len(rows),'median_seconds':statistics.median(r['seconds'] for r in rows.values())}
            if mode!='decode_filter' and len({r['output_sha256'] for r in report['rows'] if r['mode']==mode})!=1:
                raise RuntimeError('Same-stage Native/Stock encoded files differ')
            ratios=[];randomizer=random.Random(202611048)
            for _ in range(10000):
                sample=randomizer.choices(sorted(groups['native']),k=5)
                ratios.append(statistics.median(groups['native'][i]['seconds'] for i in sample)/statistics.median(groups['stock'][i]['seconds'] for i in sample))
            ratios.sort()
            report['comparisons'][mode]={'native_stock_median_ratio':report['summary'][mode+'/native']['median_seconds']/report['summary'][mode+'/stock']['median_seconds'],
                'paired_bootstrap_ratio_95_percent':[ratios[250],ratios[9749]],'matched_pixels':True}
        if sha256_file(raw)!=checksum or sha256_file(source)!=report['source_sha256']:
            raise RuntimeError('Diagnostic input changed')
        report['status']='completed';save()
    except BaseException as error:
        report.update(status='failed',error=str(error)[:4000]);save();raise
    print(json.dumps({'report':str(path),'comparisons':report['comparisons']}))


if __name__=='__main__': main()
