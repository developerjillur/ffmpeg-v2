#!/usr/bin/python3 -B
"""Official Netflix open-content HDR object; TLS/ETag-bound resumable local QA।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import json
from pathlib import Path
import sys

from acquire_phase4_corpus import Guard, download
from ffv2.io import sha256_file,write_json
from ffv2.media import probe_path

DIRECTORY=Path(str(lab_path('ffmpeg-v2-phase5/hdr-corpus')))
URL='https://s3.amazonaws.com/download.opencontent.netflix.com/Chimera/Chimera_DCI4k2398p_HDR_P3PQ.mp4'
LICENCE='https://s3.amazonaws.com/download.opencontent.netflix.com/Chimera/creative-commons-attribution-4-intl-public-license.txt'
BYTES=2533440911

def main():
    directory=DIRECTORY
    directory.mkdir(parents=True,exist_ok=True)
    guard=Guard(directory)
    target=directory/'Chimera_DCI4k2398p_HDR_P3PQ.mp4'
    path=directory/'receipt.json'
    if path.exists():
        import os,uuid
        os.link(path,path.with_name('receipt-'+uuid.uuid4().hex+'.previous.json'))
    report={'status':'running','url':URL,'licence':'CC BY 4.0','licence_url':LICENCE,'source_page':'https://opencontent.netflix.com/',
            'attribution':'Chimera, Netflix Open Content; CC BY 4.0; technical HDR-to-SDR derivative QA.',
            'estimated_storage_bytes':4*1024**3,'estimated_memory_bytes':256*1024**2}
    try:
        report['download']=download(URL,target,BYTES,guard)
        if target.stat().st_size!=BYTES:
            raise RuntimeError('Official object byte size mismatch')
        licence=directory/'CC-BY-4.0.txt'
        report['licence_download']=download(LICENCE,licence,65536,guard)
        prefix=Path(sys.argv[1]).resolve(strict=True)
        media=probe_path(target,str(prefix/'bin/ffprobe'))
        if media['video'].get('color_transfer')!='smpte2084':
            raise RuntimeError('Downloaded source is not tagged PQ HDR')
        report.update(status='completed',media=media,source_sha256=sha256_file(target),source=str(target))
    except BaseException as error:
        report.update(status='failed',error=str(error)[:3000])
        raise
    finally:
        write_json(path,report)
    print(json.dumps({'receipt':str(path),'video':report['media']['video'],'duration_seconds':report['media']['duration_seconds']}))

if __name__=='__main__':main()
