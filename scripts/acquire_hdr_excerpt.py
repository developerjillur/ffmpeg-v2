#!/usr/bin/python3 -B
"""Retained Netflix prefix ও verified moov range থেকে bounded complete HDR excerpt।"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import time
import urllib.request
import uuid

from acquire_phase4_corpus import Guard
from acquire_hdr import DIRECTORY,URL,BYTES,LICENCE
from verify_phase5 import Check
from ffv2.io import capture,sha256_file,write_json

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--prefix',required=True,type=Path)
    args=parser.parse_args()
    directory=DIRECTORY/('excerpt-'+time.strftime('%Y%m%dT%H%M%S',time.gmtime())+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    verify=Check(args.prefix.resolve(strict=True),directory)
    guard=Guard(directory)
    partial=DIRECTORY/'Chimera_DCI4k2398p_HDR_P3PQ.mp4.part'
    identity=json.loads((DIRECTORY/'Chimera_DCI4k2398p_HDR_P3PQ.mp4.download.json').read_text())
    if identity['url']!=URL or identity['bytes']!=BYTES or not 1024**2<partial.stat().st_size<64*1024**2:
        raise RuntimeError('Bounded retained publisher prefix is required')
    # Fixed trusted MP4 top-level boxes are checked, never guessed offsets.
    with partial.open('rb') as source:
        position=0
        for _ in range(16):
            source.seek(position);header=source.read(16)
            size,kind=struct.unpack('>I4s',header[:8])
            if size==1:size=struct.unpack('>Q',header[8:16])[0]
            if kind==b'mdat':
                tail_start=position+size
                break
            if size<8 or position+size>partial.stat().st_size:
                raise RuntimeError('Unexpected MP4 prefix')
            position+=size
        else:raise RuntimeError('mdat not found in retained prefix')
    if not 8<BYTES-tail_start<1024**2:
        raise RuntimeError('Tail metadata range exceeds bound')
    request=urllib.request.Request(URL,headers={'Range':f'bytes={tail_start}-{BYTES-1}','If-Match':identity['etag']})
    with urllib.request.urlopen(request,timeout=30) as response:
        if response.status!=206 or response.headers.get('ETag')!=identity['etag'] or response.headers.get('Content-Range')!=f'bytes {tail_start}-{BYTES-1}/{BYTES}':
            raise RuntimeError('Publisher did not confirm the exact same object byte range')
        tail=response.read(BYTES-tail_start+1)
    if len(tail)!=BYTES-tail_start or tail[4:8]!=b'moov' or struct.unpack('>I',tail[:4])[0]!=len(tail):
        raise RuntimeError('Complete bounded moov atom not observed')
    tail_path=directory/'publisher-moov.bin';tail_path.write_bytes(tail)
    sparse=directory/'incomplete-range-source.mp4'
    print(json.dumps({'new_sparse_source':str(sparse),'logical_bytes':BYTES,'copied_prefix_bytes':partial.stat().st_size,'tail_bytes':len(tail)}),flush=True)
    with partial.open('rb') as incoming,sparse.open('xb') as output:
        shutil.copyfileobj(incoming,output,length=1024**2)
        output.seek(tail_start);output.write(tail);output.truncate(BYTES);output.flush();os.fsync(output.fileno())
    binary=verify.caps['ffmpeg'];probe=verify.caps['ffprobe']
    # Inspect a bounded packet prefix. Only packets wholly inside actual fetched
    # bytes may be copied; the sparse source is never a valid full-movie asset.
    code,out,err=capture([probe,'-v','error','-probesize','65536','-analyzeduration','50000','-threads','1','-select_streams','v:0',
        '-read_intervals','%+#40','-show_packets','-show_data_hash','sha256','-show_entries','packet=pos,size,flags,data_hash:stream=codec_name,width,height,pix_fmt,color_primaries,color_transfer,color_space,color_range',
        '-of','json',str(sparse)],timeout=60,memory_limit=512*1024**2)
    if code:raise RuntimeError(err[-2000:])
    packets=json.loads(out)['packets']
    available=[]
    for packet in packets:
        if int(packet['pos'])+int(packet['size'])>partial.stat().st_size:break
        available.append(packet)
    count=min(12,max(1,len(available)-4))
    if not available or 'K' not in available[0]['flags']:
        raise RuntimeError('No complete leading video keyframe in fetched prefix')
    excerpt=directory/'complete-hdr-excerpt.mp4'
    verify.aux('hdr-packet-copy',[binary,'-v','error','-nostdin','-n','-probesize','65536','-analyzeduration','50000','-threads','1',
        '-i',str(sparse),'-map','0:v:0','-an','-frames:v',str(count),'-c:v','copy','-map_metadata','-1','-movflags','+faststart',
        '-fs',str(64*1024**2),str(excerpt)],excerpt,budget=64*1024**2)
    code,raw,err=capture([probe,'-v','error','-select_streams','v:0','-show_packets','-show_data_hash','sha256','-show_entries','packet=data_hash',
        '-of','json',str(excerpt)],timeout=30)
    if code or [p['data_hash'] for p in json.loads(raw)['packets']]!=[p['data_hash'] for p in available[:count]]:
        raise RuntimeError('Excerpt packet payload did not match the authenticated fetched bytes')
    from ffv2.media import probe_path
    metadata=probe_path(excerpt,probe)
    video=metadata['video']
    verify.report.update(source_url=URL,object_identity=identity,source_excerpt=str(excerpt),source_excerpt_sha256=sha256_file(excerpt),
        prefix_sha256=sha256_file(partial),tail_sha256=sha256_file(tail_path),downloaded_prefix_bytes=partial.stat().st_size,
        exact_tail_range=[tail_start,BYTES-1],metadata=metadata,
        scope='Complete video-only excerpt from actual publisher packet bytes; incomplete sparse reconstruction is acquisition-only, not a full downloaded movie.',
        licence='CC BY 4.0',licence_url=LICENCE,attribution='Chimera, Netflix Open Content; technical packet excerpt and HDR-to-SDR derivatives.')
    try:
        if video.get('color_transfer')!='smpte2084':
            verify.aux('excerpt-full-decode',[binary,'-v','error','-nostdin','-xerror','-threads','1','-err_detect','explode','-i',str(excerpt),'-an','-threads','1','-f','null','-'],excerpt)
            verify.refused('untagged_publisher_hdr_refusal',{'operation':'transcode','input':str(excerpt),'output':str(directory/'not-inferred.mp4'),
                'encoder':'software','hdr_policy':'tone_map','source_peak_nits':1000},{'hdr_metadata_required'})
            verify.report.update(status='completed',source_frames=count,classification='Publisher filename says HDR_P3PQ; fetched H264 stream is 8-bit and lacks colour signalling. No HDR signal was inferred, re-labelled, or tone mapped.',
                                 real_hdr_positive_test=False)
            verify.save()
            print(json.dumps({'report':str(directory/'report.json'),'source_frames':count,'metadata_inference':False,'source_video':video}))
            return
        # Peak is explicitly declared for this QA transform, never inferred from
        # appearance or promoted as a colourist-approved mastering value.
        image=verify.media('real-hdr-png',{'operation':'frame','input':str(excerpt),'output':str(directory/'real-hdr-srgb.png'),
            'hdr_policy':'tone_map','source_peak_nits':1000,'max_width':1920,'max_height':1080})
        sdr=verify.media('real-hdr-video',{'operation':'transcode','input':str(excerpt),'output':str(directory/'real-hdr-sdr.mp4'),
            'hdr_policy':'tone_map','source_peak_nits':1000,'encoder':'software','max_width':1920,'max_height':1080})
        if int(sdr['receipt']['validation']['full_decode']['last_progress']['frame'])!=count:
            raise RuntimeError('Complete HDR excerpt decode/frame count mismatch')
        verify.passed('real_hdr_excerpt',source_frames=count,source_video=video,declared_qa_peak_nits=1000,payloads_preserved=True,
            image=image['output'],video=sdr['output'],limitation='Short real content/metadata and full-decode proof; peak is a declared QA setting, not perceptual mastering approval.')
        verify.report['status']='completed'
    except BaseException as error:
        verify.report.update(status='failed',error=str(error)[:5000]);raise
    finally:
        verify.save()
    print(json.dumps({'report':str(directory/'report.json'),'source_frames':count,'source_video':video}))

if __name__=='__main__':main()
