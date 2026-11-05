#!/usr/bin/python3 -B
"""Phase 2-এর bounded media, GPU, fault ও wall-clock acceptance।"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
import uuid
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.capabilities import capabilities
from ffv2.config import Settings
from ffv2.controller import SupervisorSession
from ffv2.errors import FFV2Error
from ffv2.io import capture, digest, sha256_file, write_json
from ffv2.media import probe_path
from ffv2.planner import build_plan
from ffv2.resources import snapshot
from ffv2.store import Store
from ffv2.worker import host_lock, supervised, work


class Verification:
    def __init__(self, prefix, directory, *, sparse_source=None, main10_source=None, natural_proof=None):
        self.prefix, self.directory = prefix, directory
        self.sparse_source, self.main10_source = sparse_source, main10_source
        self.natural_proof = natural_proof
        directory.mkdir(parents=True, exist_ok=True)
        self.settings = Settings(state=directory / "state", ffmpeg=str(prefix / "bin/ffmpeg"), ffprobe=str(prefix / "bin/ffprobe"))
        self.caps = capabilities(self.settings)
        self.store = Store(self.settings)
        self.report = {"schema_version": 1, "status": "running", "directory": str(directory), "install_prefix": str(prefix),
                       "binary_version": self.caps["ffmpeg_version"], "tests": {}}

    def save(self):
        write_json(self.directory / "report.json", self.report)

    def aux(self, name, argv, output, *, timeout=120, budget=256 * 1024 ** 2, environment=None):
        diagnostic = self.directory / (name + "-" + uuid.uuid4().hex[:8] + ".diagnostic.json")
        plan = {"kind": "diagnostic", "spec": {"operation": name, "output": str(diagnostic)},
                "estimates": {"job_memory_bytes": 2 * 1024 ** 3, "output_budget_bytes": budget}, "timeout_seconds": timeout}
        plan["plan_id"] = digest(plan)
        queued = self.store.enqueue(plan); job = self.store.claim(queued["id"])
        attempt = self.store.root / "jobs" / job["id"] / "attempt-001"; attempt.mkdir(parents=True)
        try:
            with host_lock(self.settings) as lock_fd:
                receipt = supervised(argv, name, job, attempt, self.settings, snapshot(self.directory), lock_fd, output,
                                     environment=environment)
            self.store.update(job["id"], "completed", receipt=receipt)
            write_json(diagnostic, receipt)
            return receipt
        except BaseException:
            self.store.update(job["id"], "failed")
            raise

    def media(self, name, spec, *, failed=False):
        plan = build_plan(spec, self.settings, self.caps)
        queued = self.store.enqueue(plan)
        work(self.settings, job_id=queued["id"])
        result = self.store.get(queued["id"], plan=False)
        write_json(self.directory / (name + ".job.json"), result)
        if (result["status"] == "completed") == failed:
            raise RuntimeError(name + ": " + json.dumps(result.get("error"), ensure_ascii=False))
        if failed and Path(spec["output"]).exists():
            raise RuntimeError("Failed job published output")
        return result

    def generate(self, name, source, filters, *, duration=2, codec="ffv1", extra=(), pix_fmt="yuv420p"):
        output = self.directory / (name + ".mkv")
        args = [self.caps["ffmpeg"], "-v", "error", "-nostdin", "-n", "-filter_threads", "1", "-f", "lavfi", "-i", source]
        if filters:
            args += ["-vf", filters]
        args += ["-t", str(duration), "-fps_mode", "vfr", "-c:v", codec, "-threads", "1", "-pix_fmt", pix_fmt,
                 *extra, "-fs", str(128 * 1024 ** 2), str(output)]
        self.aux(name, args, output)
        return output

    def frame_times(self, path):
        code, raw, err = capture([self.caps["ffprobe"], "-v", "error", "-select_streams", "v:0", "-show_frames",
                                  "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(path)], timeout=30)
        if code: raise RuntimeError(err[-2000:])
        return [float(f["best_effort_timestamp_time"]) for f in json.loads(raw)["frames"]]

    def media_matrix(self):
        tests = self.report["tests"]
        # Real interlaced flag and temporal weaving; both typed software and GPU paths consume it.
        interlaced = self.generate("interlaced", "testsrc2=size=320x180:rate=60:duration=2", "tinterlace=mode=interleave_top",
                                   codec="libx264", extra=("-preset", "veryfast", "-flags", "+ilme+ildct", "-x264-params", "tff=1"))
        metadata = probe_path(interlaced, self.caps["ffprobe"])
        if metadata["video"].get("field_order") in (None, "unknown", "progressive"):
            raise RuntimeError("Interlace fixture not actually tagged interlaced")
        result = self.media("deinterlace", {"operation":"transcode", "input":str(interlaced), "output":str(self.directory/"deinterlaced.mp4"),
                                             "encoder":"software", "deinterlace":"bwdif"})
        if len(self.frame_times(Path(result["output"]))) != 60:
            raise RuntimeError("Deinterlace send_frame changed frame count")
        tests["deinterlace"] = {"status":"pass", "source_field_order":metadata["video"]["field_order"], "frames":60}
        self.media("deinterlace-sheet", {"operation":"contact_sheet", "input":str(interlaced),
                    "output":str(self.directory/"deinterlaced-sheet.jpg"), "count":4, "deinterlace":"bwdif"})
        tests["deinterlace_sheet"] = {"status":"pass"}
        self.save()
        # Runtime Metal execution is compared against the installed offline-compiled shader.
        for format_name in ("nv12", "p010le"):
            outputs, receipts = {}, {}
            for engine, binary in (("installed", "/opt/homebrew/bin/ffmpeg"), ("native", self.caps["ffmpeg"])):
                output = self.directory / ("metal-" + format_name + "-" + engine + ".framemd5")
                graph = f"format={format_name},hwupload,yadif_videotoolbox=mode=send_frame:deint=all,hwdownload,format={format_name}"
                command = [binary, "-v", "info", "-nostdin", "-n", "-init_hw_device", "videotoolbox=vt", "-filter_hw_device", "vt",
                     "-filter_threads", "1", "-threads", "1", "-i", str(interlaced), "-vf", graph, "-an", "-threads", "1",
                     "-flush_packets", "1", "-f", "framemd5", str(output)]
                try:
                    receipts[engine] = self.aux("metal-" + engine + "-" + format_name, command, output)
                except FFV2Error as error:
                    path = error.payload().get("details", {}).get("receipt")
                    failed = json.loads(Path(path).read_text()) if path else {}
                    if engine != "installed" or failed.get("exit_code") != -11 or failed.get("reasons"):
                        raise
                    receipts[engine] = failed
                outputs[engine] = [l for l in output.read_text().splitlines() if not l.startswith("#")]
            if outputs["installed"] != outputs["native"] or len(outputs["native"]) != 60:
                raise RuntimeError("Metal shader output mismatch")
            if "Compiling Metal shader at runtime" not in receipts["native"]["stderr_tail"]:
                raise RuntimeError("Metal runtime branch did not execute")
            tests["metal_" + format_name] = {"status":"pass", "frames":60, "frame_hashes_equal":True,
                                           "native_exit_code":receipts["native"]["exit_code"], "installed_exit_code":receipts["installed"]["exit_code"],
                                           "comparison_scope":"Stock per-packet-flushed 60 frame hashes retained even if its cleanup crashes; native must exit 0",
                                           "native_wall_seconds":receipts["native"]["wall_seconds"],
                                           "installed_wall_seconds":receipts["installed"]["wall_seconds"]}
            self.save()
        # Synthetic known transfer function, colour metadata and finite monotonic pixels.
        for transfer in ("smpte2084", "arib-std-b67"):
            hdr = self.generate("hdr-"+transfer, "testsrc2=size=320x180:rate=15:duration=2",
                    "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc="+transfer+":colorspace=bt2020nc:range=limited",
                    pix_fmt="yuv420p10le", codec="libx265", extra=("-preset","ultrafast","-x265-params",
                    "pools=1:frame-threads=1:wpp=0:log-level=error:lossless=1","-color_primaries","bt2020","-color_trc",transfer,"-colorspace","bt2020nc","-color_range","tv"))
            result = self.media("tone-map-"+transfer, {"operation":"transcode", "input":str(hdr), "output":str(self.directory/(transfer+"-sdr.mp4")),
                    "hdr_policy":"tone_map", "source_peak_nits":1000, "encoder":"software"})
            output = result["receipt"]["validation"]["metadata"]["video"]
            if any("mastering" in d.get("side_data_type", "").lower() or "content light" in d.get("side_data_type", "").lower()
                   for d in output.get("side_data_list", [])):
                raise RuntimeError("Stale HDR side data survived SDR conversion")
            tests["tone_map_"+transfer] = {"status":"pass", "frames":len(self.frame_times(Path(result["output"]))),
                    "output_tags":{k:output[k] for k in ("color_primaries","color_transfer","color_space","color_range")},
                    "scope":"Synthetic transfer-tagged 10-bit signal; no natural HDR perceptual acceptance"}
            self.save()
        self.pq_ramp()
        vfr = self.generate("vfr", "testsrc2=size=320x180:rate=30:duration=2",
                            "setpts='if(lt(N,30),N/(30*TB),(1+(N-30)/15)/TB)'", duration=3)
        result = self.media("vfr", {"operation":"transcode", "input":str(vfr), "output":str(self.directory/"vfr.mp4"), "encoder":"software"})
        before, after = self.frame_times(vfr), self.frame_times(Path(result["output"]))
        if len(before) != 60 or len(after) != 60 or max(abs(a-b) for a,b in zip(before,after)) > 0.002:
            raise RuntimeError("VFR frame count/timestamps changed")
        tests["vfr"] = {"status":"pass", "frames":60, "max_timestamp_delta_seconds":max(abs(a-b) for a,b in zip(before,after))}
        refusal=self.media("unsupported-hardware-decode",{"operation":"transcode","input":str(vfr),
                "output":str(self.directory/"no-fallback.mp4"),"encoder":"software","decode":"videotoolbox"},failed=True)
        tests["no_software_decode_fallback"]={"status":"pass","failure_code":refusal["error"]["code"],"published":False}
        source = self.generate("rotation-base", "testsrc2=size=128x96:rate=15:duration=2", "", codec="libx264", extra=("-preset","veryfast"))
        rotated = self.directory/"rotated.mp4"
        self.aux("rotation", [self.caps["ffmpeg"],"-v","error","-nostdin","-n","-display_rotation:v:0","90","-i",str(source),"-c","copy",str(rotated)],rotated)
        result = self.media("rotation-output", {"operation":"transcode","input":str(rotated),"output":str(self.directory/"rotation-output.mp4"),"encoder":"software"})
        if result["receipt"]["validation"]["metadata"]["video"]["width"] != 96:
            raise RuntimeError("Rotation was not applied")
        tests["rotation"] = {"status":"pass", "output_width":96, "output_height":128}
        broken = self.directory/"truncated.mkv"; data = vfr.read_bytes(); broken.write_bytes(data[:len(data)//2])
        result = self.media("truncated", {"operation":"transcode","input":str(broken),"output":str(self.directory/"truncated.mp4"),"encoder":"software"}, failed=True)
        tests["truncated"] = {"status":"pass", "failure_code":result["error"]["code"], "published":False}
        playlist = self.directory/"network.m3u8"
        playlist.write_text("#EXTM3U\n#EXT-X-TARGETDURATION:2\n#EXTINF:2,\nhttp://127.0.0.1:9/never-fetch.ts\n#EXT-X-ENDLIST\n")
        try:
            build_plan({"operation":"remux","input":str(playlist),"output":str(self.directory/"network.mkv")},self.settings,self.caps)
            raise RuntimeError("Network playlist unexpectedly accepted")
        except FFV2Error as error:
            tests["network_playlist"] = {"status":"pass", "failure_code":error.code}
        self.save()

    def pq_ramp(self):
        width,height=256,64
        def pq(nits):
            m1,m2,c1,c2,c3=2610/16384,2523/32,3424/4096,2413/128,2392/128
            value=(nits/10000)**m1
            return ((c1+c2*value)/(1+c3*value))**m2
        row=[round(64+876*pq(1000*x/(width-1))) for x in range(width)]
        values=array("H",row*height+[512]*(width*height//2))
        if sys.byteorder!="little": values.byteswap()
        raw=self.directory/"pq-ramp.yuv";raw.write_bytes(values.tobytes()*4)
        source=self.directory/"pq-ramp.mkv"
        self.aux("pq-ramp-source",[self.caps["ffmpeg"],"-v","error","-nostdin","-n","-f","rawvideo","-pixel_format","yuv420p10le",
            "-video_size",f"{width}x{height}","-framerate","2","-i",str(raw),"-c:v","libx265","-preset","ultrafast",
            "-vf","setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc:range=limited",
            "-x265-params","pools=1:frame-threads=1:wpp=0:log-level=error:lossless=1","-threads","1","-pix_fmt","yuv420p10le",
            "-color_primaries","bt2020","-color_trc","smpte2084","-colorspace","bt2020nc","-color_range","tv",str(source)],source)
        result=self.media("pq-ramp",{"operation":"transcode","input":str(source),"output":str(self.directory/"pq-ramp-sdr.mp4"),
                    "hdr_policy":"tone_map","source_peak_nits":1000,"encoder":"software"})
        decoded=self.directory/"pq-ramp-sdr.yuv"
        self.aux("pq-ramp-decode",[self.caps["ffmpeg"],"-v","error","-nostdin","-n","-threads","1","-i",result["output"],
                "-frames:v","1","-pix_fmt","yuv420p","-threads","1","-f","rawvideo",str(decoded)],decoded)
        plane=decoded.read_bytes()[:width*height]
        def hable(value):
            return (value*(.15*value+.50*.10)+.20*.02)/(value*(.15*value+.50)+.20*.30)-.02/.30
        samples=[]
        for x in (0,16,32,64,96,128,160,192,224,255):
            linear=hable(10*x/(width-1))/hable(10)
            # zimg's default display-referred BT.709 path uses inverse BT.1886.
            gamma=max(0,linear)**(1/2.4)
            expected=16+219*gamma
            observed=sum(plane[y*width+x] for y in range(16,48))/32
            samples.append({"x":x,"input_nits":1000*x/(width-1),"expected_y":expected,"observed_y":observed,"error":abs(expected-observed)})
        maximum=max(s["error"] for s in samples)
        if maximum>5 or any(b["observed_y"]<a["observed_y"]-1 for a,b in zip(samples,samples[1:])):
            raise RuntimeError("PQ ramp does not match independent Hable plus BT.709 calculation: "+str(maximum))
        self.report["tests"]["pq_analytic_ramp"]={"status":"pass","max_luma_error_8bit":maximum,"tolerance":5,"samples":samples,
                 "scope":"Known neutral PQ ramp, independent ST2084/Hable/BT1886 display-gamma formulas; excludes perceptual colour-volume/HDR display acceptance"}
        self.save()

    def natural_corpus(self):
        # Private test-only copies; collection's copyright caveat is retained in provenance.
        corpus = self.directory/"corpus"; corpus.mkdir()
        for name, file_name, maximum in (("talking", "akiyo_qcif.y4m", 12*1024**2), ("motion", "bus_qcif_15fps.y4m", 4*1024**2)):
            source = corpus/file_name
            url = "https://media.xiph.org/video/derf/y4m/" + file_name
            if self.natural_proof:
                retained=json.loads(self.natural_proof.read_text())
                record=retained.get('tests',{}).get('natural_'+name,{})
                source=self.natural_proof.parent/'corpus'/file_name
                if retained.get('status')!='completed' or record.get('status')!='pass' or record.get('source_url')!=url or not source.is_file() or source.stat().st_size>maximum or sha256_file(source)!=record.get('source_sha256'):
                    raise RuntimeError('Retained publisher fixture/proof identity mismatch')
            else:
                with urllib.request.urlopen(url, timeout=30) as remote, source.open("xb") as local:
                    total = 0
                    while True:
                        data = remote.read(128*1024)
                        if not data: break
                        total += len(data)
                        if total > maximum: raise RuntimeError("Corpus download exceeds budget")
                        local.write(data)
            converted = corpus/(name+".mkv")
            self.aux("corpus-"+name, [self.caps["ffmpeg"],"-v","error","-nostdin","-n","-threads","1","-i",str(source),
                     "-c:v","ffv1","-threads","1","-fs",str(64*1024**2),str(converted)],converted)
            result = self.media("corpus-"+name, {"operation":"transcode","input":str(converted),"output":str(corpus/(name+".mp4")),"encoder":"software"})
            before, after = self.frame_times(converted), self.frame_times(Path(result["output"]))
            if len(before) != len(after): raise RuntimeError("Natural corpus frame count changed")
            self.report["tests"]["natural_"+name] = {"status":"pass","source_url":url,"source_sha256":sha256_file(source),
                        "bytes":source.stat().st_size,"frames":len(after),"output_bytes":result["receipt"]["output_bytes"],
                        "copyright_context":"https://media.xiph.org/video/derf/ ; believed freely redistributable, additional restrictions may apply; private QA only"}
            self.save()

    def sparse(self):
        source = self.sparse_source or ROOT/".runtime/verification/large-media-20261102T145846-87377acc/ten-minute.mp4"
        if not source.is_file(): raise RuntimeError("Provide --sparse-source from a completed 600s verification fixture")
        trials = []
        for trial in range(3):
            results = {}
            for method in (("single_pass","seek") if trial % 2 == 0 else ("seek","single_pass")):
                result = self.media("sparse-"+method+"-"+str(trial), {"operation":"contact_sheet","input":str(source),
                            "output":str(self.directory/("sparse-"+method+"-"+str(trial)+".jpg")),"duration":600,"count":8,"columns":4,"sampling":method})
                results[method] = result
            a,b = [results[m]["receipt"]["contact_sheet"]["source_pts_seconds"] for m in ("single_pass","seek")]
            if any(abs(x-y)>0.001 for x,y in zip(a,b)):
                raise RuntimeError("Sparse seek differs from full-decode sample timestamps")
            hashes = []
            for method in ("single_pass","seek"):
                image = Path(results[method]["output"])
                code,out,err = capture([self.caps["ffmpeg"],"-v","error","-threads","1","-i",str(image),"-threads","1","-f","framemd5","-"],timeout=30)
                if code: raise RuntimeError(err[-1000:])
                hashes.append([l for l in out.splitlines() if not l.startswith("#")])
            if hashes[0] != hashes[1]: raise RuntimeError("Sparse mosaic decoded pixels differ")
            trials.append({m:results[m]["receipt"]["phase_timings_seconds"] for m in results})
        medians = {m:{key:statistics.median(t[m][key] for t in trials) for key in trials[0][m]} for m in ("single_pass","seek")}
        self.report["tests"]["sparse_sampling"] = {"status":"pass","source":str(source),"source_sha256":sha256_file(source),
                    "samples":a,"decoded_pixels_equal":True,
                    "timing_seconds":medians,"trials":trials,
                    "scope":"Three matched 600s synthetic timeline trials, alternating order, no warmup exclusion; not a general seek speed claim"}
        self.save()

    def large_reuse(self):
        source=self.main10_source or ROOT/".runtime/verification/large-media-20261102T145846-87377acc/main10-4k.mp4"
        if not source.is_file(): raise RuntimeError("Provide --main10-source from a completed 4K SDR Main10 fixture")
        before=sha256_file(source)
        metadata=probe_path(source,self.caps["ffprobe"])
        video=metadata["video"]
        if (video["width"],video["height"],video["codec_name"],video["pix_fmt"])!=(3840,2160,"hevc","yuv420p10le"):
            raise RuntimeError("Expected 4K HEVC Main10 fixture")
        self.aux("4k-main10-hwdecode",[self.caps["ffmpeg"],"-v","error","-xerror","-nostdin","-threads","2","-filter_threads","1",
                "-hwaccel","videotoolbox","-hwaccel_output_format","videotoolbox_vld","-i",str(source),"-an","-vf","hwdownload,format=p010le",
                "-threads","2","-f","null","-"],source)
        encoded=self.media("4k-main10-transcode",{"operation":"transcode","input":str(source),"output":str(self.directory/"main10-1080p.mp4"),
                "encoder":"videotoolbox","decode":"videotoolbox","max_width":1920,"max_height":1080,"fps":30})
        if not encoded["receipt"].get("hardware_decode_runtime_verified"): raise RuntimeError("Typed hardware decode was not verified")
        result=self.media("4k-main10-remux",{"operation":"remux","input":str(source),"output":str(self.directory/"main10-remux.mkv")})
        actual=result["receipt"]["validation"]["metadata"]["video"]
        for key in ("pix_fmt","color_transfer","color_primaries","color_space","width","height"):
            if actual.get(key)!=metadata["video"].get(key): raise RuntimeError("Main10 remux metadata changed")
        if sha256_file(source)!=before: raise RuntimeError("Retained Main10 source changed")
        self.report["tests"]["main10_4k"]={"status":"pass","source":str(source),"source_sha256":before,"hardware_download_p010":True,
                "hardware_transcode":True,"remux_metadata_preserved":True,"source_unchanged":True}
        self.save()

    def faults(self):
        for mode in ("parent-loss","cancel","timeout"):
            area = self.directory/mode; area.mkdir()
            with (area/'helper.stderr').open('wb') as diagnostic:
                child = subprocess.Popen([sys.executable,"-B",str(Path(__file__).resolve()),"--prefix",str(self.prefix),
                            "--directory",str(area),"--helper",mode],stdout=subprocess.DEVNULL,stderr=diagnostic,
                            start_new_session=True)
            try:
                deadline = time.monotonic()+20
                while not (area/"helper.json").is_file():
                    if child.poll() is not None or time.monotonic()>deadline: raise RuntimeError("Fault helper failed to start")
                    time.sleep(0.1)
                info = json.loads((area/"helper.json").read_text()); store = Store(Settings.load(state=info["state"]))
                while not store.get(info["job_id"],plan=False).get("progress"):
                    if child.poll() is not None or time.monotonic()>deadline: raise RuntimeError("Fault helper produced no live progress")
                    time.sleep(0.1)
                if mode=="parent-loss": child.kill()
                elif mode=="cancel": store.cancel(info["job_id"])
                child.wait(timeout=12)
                receipt_path = Path(info["receipt"])
                while not receipt_path.is_file():
                    if time.monotonic()>deadline+10: raise RuntimeError("Fault supervisor produced no receipt")
                    time.sleep(0.1)
                receipt = json.loads(receipt_path.read_text())
                expected = {"parent-loss":"worker_parent_lost","cancel":"cancelled","timeout":"timeout"}[mode]
                if receipt["status"]!="stopped" or expected not in receipt["reasons"]: raise RuntimeError("Incorrect fault stop reason")
                code, out, err = capture(["/bin/ps","-p",str(receipt["process_pid"]),"-o","pid="],timeout=3)
                if out.strip(): raise RuntimeError("Owned media process survived fault")
                released=False
                for _ in range(30):
                    try:
                        with host_lock(self.settings): pass
                        released=True;break
                    except FFV2Error as error:
                        if error.code!="worker_busy": raise
                        time.sleep(0.1)
                if not released: raise RuntimeError("Fault supervisor kept host lock")
                store.recover()
                self.report["tests"][mode] = {"status":"pass","stop_reason":expected,"process_gone":True,"host_lock_released":True,
                                             "supervisor_receipt":str(receipt_path)}
                self.save()
            finally:
                if child.poll() is None: child.terminate(); child.wait(timeout=10)

    def soak(self):
        output = self.directory/"wall-clock-soak.mp4"
        receipt = self.aux("soak",[self.caps["ffmpeg"],"-v","error","-nostdin","-n","-nostats","-progress","pipe:1",
                "-progress_format","jsonl","-init_hw_device","videotoolbox=vt","-filter_hw_device","vt","-filter_threads","1",
                "-re","-f","lavfi","-i","testsrc2=size=320x180:rate=30:duration=90",
                "-vf","format=nv12,hwupload,yadif_videotoolbox=deint=all,hwdownload,format=nv12",
                "-c:v","libx264","-preset","veryfast","-threads","1","-t","90","-fs",str(128*1024**2),str(output)],output,timeout=120)
        metadata = probe_path(output,self.caps["ffprobe"])
        self.aux("soak-decode",[self.caps["ffmpeg"],"-v","error","-xerror","-nostdin","-threads","1","-i",str(output),"-threads","1","-f","null","-"],output)
        if receipt["wall_seconds"]<85 or receipt["resource_sample_count"]<80 or abs(metadata["duration_seconds"]-90)>0.1:
            raise RuntimeError("Soak did not span a real 90s wall-clock window")
        self.report["tests"]["wall_clock_soak"] = {"status":"pass","wall_seconds":receipt["wall_seconds"],
                "duration_seconds":metadata["duration_seconds"],"resource_samples":receipt["resource_sample_count"],
                "peak_sampled_job_footprint_bytes":receipt["peak_job_memory_bytes"],"full_decode":True,
                "memory_samples":receipt["job_memory_samples"],
                "scope":"90s small synthetic real-time Metal deinterlace plus H.264 encode; not an overnight or high-resolution production soak"}
        self.save()


def helper(prefix, directory, mode):
    verification = Verification(prefix,directory)
    output = directory/"null-output"
    plan={"kind":"diagnostic","spec":{"operation":"fault","output":str(output)},
          "estimates":{"job_memory_bytes":512*1024**2,"output_budget_bytes":16*1024**2},"timeout_seconds":3 if mode=="timeout" else 45}
    plan["plan_id"]=digest(plan); queued=verification.store.enqueue(plan);job=verification.store.claim(queued["id"])
    attempt=verification.store.root/"jobs"/job["id"]/"attempt-001";attempt.mkdir(parents=True)
    write_json(directory/"helper.json",{"state":str(verification.settings.state),"job_id":job["id"],"receipt":str(attempt/"fault.request.receipt.json")})
    try:
        with host_lock(verification.settings) as fd, SupervisorSession(verification.settings,fd) as session:
            supervised([verification.caps["ffmpeg"],"-v","error","-nostdin","-nostats","-progress","pipe:1","-stats_period","0.2",
                "-re","-f","lavfi","-i","color=size=64x64:rate=10:duration=45","-threads","1","-f","null","-"],
                "fault",job,attempt,verification.settings,snapshot(directory),fd,output,session=session)
        return 1
    except FFV2Error as error:
        verification.store.update(job["id"],"interrupted",error=error.payload())
        return 0


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--prefix",required=True,type=Path)
    parser.add_argument("--directory",type=Path);parser.add_argument("--helper",choices=("parent-loss","cancel","timeout"))
    parser.add_argument("--sparse-source",type=Path);parser.add_argument("--main10-source",type=Path)
    parser.add_argument('--natural-proof',type=Path,help='Completed official Akiyo/Bus acquisition receipt reuse; no duplicate download')
    parser.add_argument("--mode",choices=("media","natural","sparse","large","faults","soak","all"),default="all")
    args=parser.parse_args();prefix=args.prefix.resolve(strict=True)
    if args.helper: return helper(prefix,args.directory,args.helper)
    directory=args.directory or ROOT/".runtime/verification"/("phase2-"+args.mode+"-"+time.strftime("%Y%m%dT%H%M%S",time.gmtime())+"-"+uuid.uuid4().hex[:8])
    verify=Verification(prefix,directory,sparse_source=args.sparse_source,main10_source=args.main10_source,natural_proof=args.natural_proof);verify.save()
    try:
        for mode,method in (("media",verify.media_matrix),("natural",verify.natural_corpus),("sparse",verify.sparse),("large",verify.large_reuse),("faults",verify.faults),("soak",verify.soak)):
            if args.mode in (mode,"all"): method()
        verify.report["status"]="completed"
    except BaseException as error:
        verify.report.update(status="failed",error=str(error)[:6000]);verify.save();raise
    verify.save();print(json.dumps({"status":"completed","report":str(directory/"report.json")},ensure_ascii=False))
    return 0


if __name__=="__main__": raise SystemExit(main())
