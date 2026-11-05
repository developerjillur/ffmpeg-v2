#!/usr/bin/python3 -B
"""Actual container/codec inputs থেকে typed output ও full decode checks।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
from pathlib import Path
import json
import time
import uuid

from verify_phase5 import Check, read_wave, amplitude
from ffv2.io import sha256_file

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prefix',required=True,type=Path)
    args=parser.parse_args()
    directory=Path(str(lab_path('ffmpeg-v2-phase7')))/('formats-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    verify=Check(args.prefix.resolve(strict=True),directory)
    d,binary=directory,verify.caps['ffmpeg']
    verify.report['script_sha256']=sha256_file(Path(__file__))
    try:
        source=d/'reference.mkv'
        verify.aux('reference',[binary,'-v','error','-nostdin','-n','-filter_threads','1','-f','lavfi','-i','testsrc2=s=320x180:r=25:d=2',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-c:v','ffv1','-threads:v','1','-c:a','pcm_s16le','-threads:a','1','-t','2',str(source)],source)
        videos={
            'mov-prores-pcm':('.mov',['-c:v','prores_ks','-profile:v','0','-pix_fmt','yuv422p10le','-c:a','pcm_s16le']),
            'avi-mjpeg-pcm':('.avi',['-c:v','mjpeg','-q:v','3','-c:a','pcm_s16le']),
            'ts-mpeg2-mp2':('.ts',['-c:v','mpeg2video','-b:v','1M','-c:a','mp2','-b:a','192k']),
            'webm-vp9-opus':('.webm',['-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-c:a','libopus']),
            'mkv-ffv1-flac':('.mkv',['-c:v','ffv1','-c:a','flac']),
            'mp4-hevc10-aac':('.mp4',['-c:v','libx265','-preset','ultrafast','-x265-params','pools=1:frame-threads=1:wpp=0:log-level=error','-pix_fmt','yuv420p10le','-c:a','aac']),
            'mkv-av1-opus':('.mkv',['-c:v','libsvtav1','-preset','12','-svtav1-params','lp=2','-c:a','libopus']),
        }
        for name,(suffix,options) in videos.items():
            fixture=d/(name+suffix)
            verify.aux(name+'-encode',[binary,'-v','error','-nostdin','-n','-filter_threads','1','-threads','1','-i',str(source),
                *options,'-threads:v','1','-threads:a','1','-fs',str(64*1024**2),str(fixture)],fixture,timeout=180,budget=64*1024**2)
            result=verify.media(name,{'operation':'transcode','input':str(fixture),'output':str(d/(name+'-normalized.mp4')),'encoder':'software'})
            frames=int(result['receipt']['validation']['full_decode']['last_progress']['frame'])
            if frames!=50:
                raise RuntimeError(name+' changed decoded frame count: '+str(frames))
            source_plan=json.loads((Path(result['receipt']['directory'])/'plan.json').read_text())['source']
            verify.passed(name,source_sha256=sha256_file(fixture),frames=frames,output_sha256=result['receipt']['output_sha256'],
                source_codec=source_plan['video']['codec_name'],source_pix_fmt=source_plan['video']['pix_fmt'],
                output_codec=result['receipt']['validation']['metadata']['video']['codec_name'])
        audios={
            'aiff-pcm':('.aiff',['-c:a','pcm_s16be']),
            'flac':('.flac',['-c:a','flac']),
            'mp3':('.mp3',['-c:a','libmp3lame','-b:a','128k']),
            'ogg-opus':('.opus',['-c:a','libopus']),
            'adts-aac':('.aac',['-c:a','aac','-b:a','128k']),
            'wav-pcm':('.wav',['-c:a','pcm_s16le']),
        }
        for name,(suffix,options) in audios.items():
            fixture=d/(name+suffix)
            verify.aux(name+'-encode',[binary,'-v','error','-nostdin','-n','-threads','1','-i',str(source),'-vn',*options,'-threads:a','1',str(fixture)],fixture)
            result=verify.media(name,{'operation':'audio','input':str(fixture),'output':str(d/(name+'-normalized.wav')),'audio_rate':16000,'audio_channels':1})
            rate,channels,count,signal=read_wave(result['output'])
            fundamental=amplitude(signal,rate,440,.25,1.25)
            if (rate,channels)!=(16000,1) or abs(count/rate-2)>.2 or not .10<fundamental<.14:
                raise RuntimeError(name+' audio content/rate/endpoints')
            verify.passed(name,source_sha256=sha256_file(fixture),samples=count,frequency_440_amplitude=fundamental)
        for suffix in ('.png','.jpg'):
            source_image=verify.media('frame'+suffix,{'operation':'frame','input':str(source),'output':str(d/('source'+suffix)),'start':.5})
            image=verify.media('image'+suffix,{'operation':'image','input':source_image['output'],'output':str(d/('resized'+suffix)),'max_width':160,'max_height':90})
            verify.passed('image'+suffix,output_sha256=image['receipt']['output_sha256'],width=160,height=90)
        verify.report['status']='completed'
    except BaseException as error:
        verify.report.update(status='failed',error=str(error)[:6000])
        raise
    finally:
        verify.save()
    print(json.dumps({'report':str(d/'report.json'),'checks':len(verify.report['tests'])}))

if __name__=='__main__':main()
