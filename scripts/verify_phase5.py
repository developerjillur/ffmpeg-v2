#!/usr/bin/python3 -B
"""Joined timestamps, visible subtitles, measured audio ও image pixels-এর acceptance।"""
from __future__ import annotations
from public_paths import lab_path, project_path
import argparse
from array import array
import json
import math
from pathlib import Path
import struct
import sys
import time
import uuid
import wave
import zlib

from verify_phase2 import Verification
from ffv2.errors import FFV2Error
from ffv2.io import capture, sha256_file, write_json
from ffv2.planner import build_plan

def png(path, width, height, depth, channels, values):
    def chunk(kind, raw):
        return struct.pack('>I', len(raw)) + kind + raw + struct.pack('>I', zlib.crc32(kind + raw))
    row = bytes(values) if depth == 8 else struct.pack('>' + 'H' * len(values), *values)
    if len(row) != width * channels * depth // 8:
        raise RuntimeError('Fixture row width')
    header = struct.pack('>IIBBBBB', width, height, depth, 6 if channels == 4 else 2, 0, 0, 0)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress((b'\0' + row) * height)) + chunk(b'IEND', b''))

def tone(path, frequency, amplitude, seconds, rate=48000):
    samples = array('h', (round(amplitude * 32767 * math.sin(2 * math.pi * frequency * n / rate)) for n in range(round(seconds * rate))))
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        output.writeframes(samples.tobytes())

def read_wave(path):
    with wave.open(str(path), 'rb') as source:
        rate, channels, frames = source.getframerate(), source.getnchannels(), source.getnframes()
        if source.getsampwidth() != 2:
            raise RuntimeError('Expected signed 16-bit PCM')
        samples = array('h', source.readframes(frames))
    if sys.byteorder != 'little':
        samples.byteswap()
    return rate, channels, frames, [s / 32768 for s in samples]

def amplitude(samples, rate, frequency, start, end):
    window = samples[round(start * rate):round(end * rate)]
    real = sum(v * math.cos(2 * math.pi * frequency * i / rate) for i, v in enumerate(window))
    imag = sum(v * math.sin(2 * math.pi * frequency * i / rate) for i, v in enumerate(window))
    return 2 * math.hypot(real, imag) / len(window)

class Check(Verification):
    def passed(self, name, **data):
        self.report['tests'][name] = {'status': 'pass', **data}
        self.save()
        print(json.dumps({'check': name, 'status': 'pass'}), flush=True)

    def raw(self, name, path, *, at=0, pix_fmt='rgb24', width=None, height=None):
        target = self.directory / (name + '.raw')
        args = [self.caps['ffmpeg'], '-v', 'error', '-nostdin', '-n', '-filter_threads', '1', '-threads', '1', '-ss', str(at), '-i', str(path), '-frames:v', '1', '-an']
        if width:
            args += ['-vf', f'scale={width}:{height}']
        args += ['-pix_fmt', pix_fmt, '-threads', '1', '-f', 'rawvideo', str(target)]
        self.aux(name, args, target, budget=8 * 1024**2)
        return target.read_bytes()

    def refused(self, name, spec, expected):
        try:
            build_plan(spec, self.settings, self.caps)
        except FFV2Error as error:
            if error.code not in expected:
                raise
            if Path(spec['output']).exists():
                raise RuntimeError('Refused output published')
            self.passed(name, code=error.code, published=False)
            return
        raise RuntimeError('Expected refusal: ' + name)

    def workflows(self):
        d, binary = self.directory, self.caps['ffmpeg']
        red, blue, black = d / 'red.mp4', d / 'blue.mp4', d / 'black.mp4'
        self.aux('red-source', [binary, '-v', 'error', '-nostdin', '-n', '-filter_threads', '1', '-f', 'lavfi', '-i', 'color=red:s=320x180:r=25:d=2', '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=2', '-c:v', 'libx264', '-preset', 'veryfast', '-threads:v', '1', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-threads:a', '1', '-t', '2', str(red)], red)
        self.aux('blue-source', [binary, '-v', 'error', '-nostdin', '-n', '-filter_threads', '1', '-f', 'lavfi', '-i', 'color=blue:s=320x240:r=24:d=1.5', '-c:v', 'libx264', '-preset', 'veryfast', '-threads:v', '1', '-pix_fmt', 'yuv420p', str(blue)], blue)
        self.aux('black-source', [binary, '-v', 'error', '-nostdin', '-n', '-filter_threads', '1', '-f', 'lavfi', '-i', 'color=black:s=640x360:r=25:d=4', '-c:v', 'libx264', '-preset', 'veryfast', '-threads:v', '1', '-pix_fmt', 'yuv420p', str(black)], black)
        joined = self.media('normalized-join', {'operation': 'concat', 'input': str(red), 'additional_inputs': [str(blue)], 'output': str(d / 'joined.mp4'), 'encoder': 'software', 'fps': 30})
        times = self.frame_times(Path(joined['output']))
        if len(times) != 105 or max(abs(t - i / 30) for i, t in enumerate(times)) > .001:
            raise RuntimeError('Joined frame count/PTS')
        for name, at, channel in [('red', .5, 0), ('blue', 2.5, 2)]:
            raw = self.raw('join-pixel-' + name, joined['output'], at=at, width=16, height=16)
            pixel = raw[(8 * 16 + 8) * 3:(8 * 16 + 8) * 3 + 3]
            if pixel[channel] < 200 or any(v > 35 for i, v in enumerate(pixel) if i != channel):
                raise RuntimeError('Joined scene order/colour')
        audio = self.media('join-audio', {'operation': 'audio', 'input': joined['output'], 'output': str(d / 'joined.wav'), 'audio_channels': 1, 'audio_rate': 48000})
        rate, _, _, signal = read_wave(audio['output'])
        rms_silent = math.sqrt(sum(s * s for s in signal[round(2.3 * rate):round(3.3 * rate)]) / rate)
        if amplitude(signal, rate, 440, .3, 1.3) < .06 or rms_silent > .001:
            raise RuntimeError('Joined audio/missing-audio silence')
        self.passed('normalize_join_timing_colour_audio', frames=105, last_pts=times[-1], silent_rms=rms_silent)
        quoted_blue = d / "blue ' [quote].mp4"
        quoted_blue.write_bytes(blue.read_bytes())
        copy = self.media('copy-join', {'operation': 'concat', 'input': str(quoted_blue), 'additional_inputs': [str(quoted_blue)], 'concat_mode': 'copy', 'output': str(d / 'copy.mkv')})
        def packets(path):
            code, out, err = capture([self.caps['ffprobe'], '-v', 'error', '-select_streams', 'v:0', '-show_packets', '-show_data_hash', 'sha256', '-show_entries', 'packet=pts_time,dts_time,data_hash', '-of', 'json', str(path)])
            if code:
                raise RuntimeError(err[-2000:])
            return json.loads(out)['packets']
        before, after = packets(blue), packets(copy['output'])
        if [p['data_hash'] for p in after] != [p['data_hash'] for p in before] * 2:
            raise RuntimeError('Copy join changed packet payloads')
        dts = [float(p['dts_time']) for p in after if 'dts_time' in p]
        decoded_pts = self.frame_times(Path(copy['output']))
        if any(b <= a for a, b in zip(dts, dts[1:])) or len(decoded_pts) != 72 or max(abs(t-i/24) for i,t in enumerate(decoded_pts)) > .0011:
            raise RuntimeError('Copy join decode/timestamps')
        self.passed('copy_join_packets', packets=len(after), payloads_equal=True, increasing_known_dts=True, decoded_frame_grid=True)
        self.refused('copy_incompatible', {'operation': 'concat', 'input': str(red), 'additional_inputs': [str(blue)], 'concat_mode': 'copy', 'output': str(d / 'bad-copy.mkv')}, {'concat_copy_incompatible'})
        primary, second = d / 'primary.wav', d / 'second.wav'
        tone(primary, 440, .15, 3)
        tone(second, 880, .1, 1)
        mixed = self.media('mix', {'operation': 'audio_mix', 'input': str(primary), 'output': str(d / 'mixed.wav'), 'audio_channels': 1, 'primary_gain_db': -6, 'mix_normalize': False, 'tracks': [{'input': str(second), 'offset': 1, 'gain_db': -6, 'loop': True}]})
        rate, channels, count, signal = read_wave(mixed['output'])
        observed = [amplitude(signal, rate, 880, a, a + .5) for a in (.2, 1.2, 2.2)]
        a440 = amplitude(signal, rate, 440, .2, .7)
        if (rate, channels, count) != (48000, 1, 144000) or observed[0] > .0002 or any(abs(v - .1 * 10**(-6/20)) > .002 for v in observed[1:]) or abs(a440 - .15 * 10**(-6/20)) > .002:
            raise RuntimeError('Audio sample/gain/offset/loop contract: ' + str(observed))
        self.passed('mix_samples_gain_offset_loop', samples=count, primary_amplitude=a440, delayed_amplitudes=observed)
        audio_join = self.media('audio-only-join', {'operation':'concat','input':str(primary),'additional_inputs':[str(second)],
            'output':str(d/'audio-joined.wav'),'audio_channels':1,'audio_rate':48000})
        rate,channels,count,signal = read_wave(audio_join['output'])
        if (rate,channels,count)!=(48000,1,192000) or amplitude(signal,rate,440,1,2)<.14 or amplitude(signal,rate,880,3.2,3.7)<.09:
            raise RuntimeError('Audio-only join order/sample endpoints')
        self.passed('audio_only_join',samples=count,order_440_then_880=True)
        hot = self.media('limit', {'operation': 'audio_mix', 'input': str(primary), 'output': str(d / 'limited.wav'), 'audio_channels': 1, 'primary_gain_db': 12, 'mix_normalize': False, 'mix_limit': .25, 'tracks': [{'input': str(primary), 'gain_db': 12}]})
        peak = max(abs(v) for v in read_wave(hot['output'])[3])
        if not .24 <= peak <= .2501:
            raise RuntimeError('Limiter peak contract: ' + str(peak))
        self.passed('mix_limiter', peak=peak, declared_limit=.25)
        self.refused('mix_outside', {'operation': 'audio_mix', 'input': str(primary), 'output': str(d / 'outside.wav'), 'tracks': [{'input': str(second), 'offset': 4}]}, {'mix_track_outside_range'})
        subtitle = d / "বাংলা ' [test].srt"
        subtitle.write_bytes('1\n00:00:00,800 --> 00:00:01,800\nবাংলা পরীক্ষা — Jillur Rahman\n'.encode('utf-16'))
        sub = self.media('bengali-subtitle', {'operation': 'subtitle', 'input': str(black), 'output': str(d / 'subtitle.mp4'), 'subtitle_file': str(subtitle), 'subtitle_font': 'bengali', 'font_size': 30, 'encoder': 'software'})
        luminance = []
        for index, at in enumerate((.2, 1.2, 2.2)):
            pixels = self.raw('subtitle-' + str(index), sub['output'], at=at)
            luminance.append(sum(v > 128 for v in pixels))
        if luminance[0] or luminance[2] or luminance[1] < 1000:
            raise RuntimeError('Subtitle visibility/timing: ' + str(luminance))
        preview = d / 'bengali-preview.png'
        self.aux('subtitle-preview', [binary, '-v', 'error', '-nostdin', '-n', '-threads', '1', '-ss', '1.2', '-i', sub['output'], '-frames:v', '1', '-threads', '1', str(preview)], preview)
        self.passed('bengali_subtitle_visible_timing', bright_channels=luminance, preview=str(preview), cue_start=.8, cue_end=1.8)
        ass_source = Path(sub['receipt']['directory'])/'ffv2-subtitles.ass'
        ass = self.media('ass-offset-range', {'operation':'subtitle','input':str(black),'output':str(d/'ass-offset.mp4'),
            'subtitle_file':str(ass_source),'subtitle_font':'bengali','start':.5,'duration':2.5,'subtitle_offset':.2,'encoder':'software'})
        lit = [sum(v>128 for v in self.raw('ass-'+str(i),ass['output'],at=at)) for i,at in enumerate((.2,.8,1.8))]
        if lit[0] or lit[2] or lit[1]<1000:
            raise RuntimeError('ASS offset/trim timing: '+str(lit))
        self.passed('ass_offset_trim_timing',bright_channels=lit,expected_output_cue=[.5,1.5])
        bad = d / 'bad.srt'
        bad.write_bytes(b'\xff\x81garbage')
        self.refused('bad_subtitle', {'operation': 'subtitle', 'input': str(black), 'output': str(d / 'bad-sub.mp4'), 'subtitle_file': str(bad)}, {'subtitle_encoding_invalid', 'subtitle_invalid', 'subtitle_empty', 'invalid_subtitle'})
        rgba = d / 'alpha.png'
        row = [v for x in range(64) for v in (255, 0, 0, 128 if x < 32 else 0)]
        png(rgba, 64, 32, 8, 4, row)
        image = self.media('alpha', {'operation': 'image', 'input': str(rgba), 'output': str(d / 'alpha-preserved.png')})
        raw = self.raw('alpha-raw', image['output'], pix_fmt='rgba')
        if raw != bytes(row) * 32:
            raise RuntimeError('PNG alpha/RGB did not roundtrip exactly')
        self.passed('png_alpha_exact', pixels=2048, sha256=sha256_file(Path(image['output'])))
        odd = d/'odd-alpha.png'
        odd_row = [v for x in range(65) for v in (x*3,90,120,128)]
        png(odd,65,33,8,4,odd_row)
        image = self.media('odd-alpha',{'operation':'image','input':str(odd),'output':str(d/'odd-preserved.png')})
        if self.raw('odd-alpha-raw',image['output'],pix_fmt='rgba')!=bytes(odd_row)*33:
            raise RuntimeError('Odd image dimensions/pixels changed')
        self.passed('odd_png_dimensions_exact',width=65,height=33)
        rgb16 = d / 'rgb16.png'
        values = [v for x in range(64) for v in (x * 1000, x * 997 + 7, 65535 - x * 1000)]
        png(rgb16, 64, 32, 16, 3, values)
        image = self.media('rgb16', {'operation': 'image', 'input': str(rgb16), 'output': str(d / 'rgb16-preserved.png')})
        raw = self.raw('rgb16-raw', image['output'], pix_fmt='rgb48be')
        if raw != struct.pack('>' + 'H' * len(values), *values) * 32:
            raise RuntimeError('PNG 16-bit values changed')
        self.passed('png_16bit_exact', pixels=2048, distinct_red_values=64)
        rgba16 = d / 'rgba16.png'
        pixel16 = (11345,22346,33457,24567)
        png(rgba16,64,32,16,4,list(pixel16)*64)
        image = self.media('rgba16-matte', {'operation':'image','input':str(rgba16),'output':str(d/'rgba16-matte.png'),'background':'#123456'})
        raw = self.raw('rgba16-matte-raw',image['output'],pix_fmt='rgb48be')
        observed = struct.unpack('>HHH',raw[:6])
        expected = [pixel16[i]*pixel16[3]/65535+value*257*(1-pixel16[3]/65535) for i,value in enumerate((18,52,86))]
        if max(abs(a-b) for a,b in zip(observed,expected))>2:
            raise RuntimeError('16-bit matte lost source precision: '+str((observed,expected)))
        self.passed('png_16bit_matte',observed=list(observed),expected=expected,tolerance_code_values=2)
        matte = self.media('matte', {'operation': 'image', 'input': str(rgba), 'output': str(d / 'white.jpg'), 'background': '#FFFFFF', 'image_quality': 2})
        raw = self.raw('matte-raw', matte['output'])
        pixel = raw[(16 * 64 + 48) * 3:(16 * 64 + 48) * 3 + 3]
        half = raw[(16 * 64 + 16) * 3:(16 * 64 + 16) * 3 + 3]
        if min(pixel) < 250 or half[0] < 250 or any(abs(v - 127) > 6 for v in half[1:]):
            raise RuntimeError('JPEG alpha matte: ' + str((list(pixel), list(half))))
        self.passed('jpeg_white_matte', transparent_pixel=list(pixel), half_alpha_pixel=list(half))
        self.pq_ramp()
        hdr = self.media('hdr-png', {'operation': 'frame', 'input': str(d / 'pq-ramp.mkv'), 'output': str(d / 'hdr-srgb.png'), 'hdr_policy': 'tone_map', 'source_peak_nits': 1000})
        values = struct.unpack('<' + 'H' * (256 * 64 * 3), self.raw('hdr-png-raw', hdr['output'], pix_fmt='rgb48le'))
        def hable(x):
            return (x * (.15*x + .05) + .004) / (x * (.15*x + .5) + .06) - .02/.30
        errors = []
        for x in (0, 16, 32, 64, 128, 192, 255):
            linear = max(0, hable(10*x/255)/hable(10))
            srgb = 12.92*linear if linear <= .0031308 else 1.055*linear**(1/2.4)-.055
            observed = values[(32*256+x)*3] / 65535
            errors.append(abs(observed-srgb))
        if max(errors) > .012:
            raise RuntimeError('Independent HDR to sRGB pixel calculation: ' + str(errors))
        self.passed('hdr_srgb_png_analytic', max_normalized_error=max(errors), tolerance=.012, tags=hdr['receipt']['validation']['metadata']['video'])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prefix', required=True, type=Path)
    parser.add_argument('--directory', type=Path)
    args = parser.parse_args()
    directory = args.directory or Path(str(lab_path('ffmpeg-v2-phase5'))) / ('acceptance-' + time.strftime('%Y%m%dT%H%M%S', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
    verify = Check(args.prefix.resolve(strict=True), directory)
    verify.report['script_sha256'] = sha256_file(Path(__file__))
    try:
        verify.workflows()
        verify.report['status'] = 'completed'
    except BaseException as error:
        verify.report.update(status='failed', error=str(error)[:6000])
        raise
    finally:
        verify.save()
    print(json.dumps({'report': str(directory / 'report.json'), 'checks': len(verify.report['tests'])}))

if __name__ == '__main__':
    main()
