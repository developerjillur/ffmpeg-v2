#!/usr/bin/python3 -B
"""একই engine-এ workflow comparison ও একই workflow-তে engine comparison।"""
from __future__ import annotations
from public_paths import lab_path, project_path

import argparse
import json
import os
import random
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASELINE=Path(str(lab_path('ffmpeg-v2-phase2/baseline')))


def case(request):
    sys.path.insert(0,request["package"])
    from ffv2 import engine
    from ffv2.capabilities import capabilities
    from ffv2.config import Settings
    from ffv2.planner import build_plan
    from ffv2.store import Store
    from ffv2.worker import work
    if request.get("selection"):
        engine.ACTIVE=Path(request["selection"])
        settings=Settings.load(state=request["state"])
    else:
        settings=Settings(state=Path(request["state"]),ffmpeg=request["ffmpeg"],ffprobe=request["ffprobe"])
    started=time.monotonic()
    caps=capabilities(settings)
    if request.get("matched_progress"):
        caps["native_jsonl_progress"] = False
    planned=time.monotonic()
    plan=build_plan(request["spec"],settings,caps)
    queued_at=time.monotonic();store=Store(settings);queued=store.enqueue(plan)
    worked_at=time.monotonic();work(settings,job_id=queued["id"])
    finished=time.monotonic();result=store.get(queued["id"],plan=False)
    if result["status"]!="completed": raise RuntimeError(str(result.get("error")))
    receipt=result["receipt"]
    value={"label":request["label"],"operation":request["spec"]["operation"],"trial":request["trial"],"warmup":request["warmup"],
           "capability_seconds":planned-started,"planning_seconds":queued_at-planned,"queue_seconds":worked_at-queued_at,
           "work_seconds":finished-worked_at,"total_seconds":finished-started,
           "encode_seconds":receipt["encode_wall_seconds"],"decode_seconds":receipt["validation_wall_seconds"],
           "phase_timings_seconds":receipt.get("phase_timings_seconds"),"sha256":receipt["output_sha256"],
           "bytes":receipt["output_bytes"],"output":result["output"],"receipt":str(Path(receipt["directory"])/"receipt.json"),
           "supervisor_reused":receipt["encoding"].get("supervisor_pid")==receipt["validation"]["full_decode"].get("supervisor_pid")
                 if "supervisor_pid" in receipt["encoding"] else None}
    print(json.dumps(value))
    return 0


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--mode",choices=("workflow","core"),default="workflow")
    parser.add_argument("--prefix",type=Path);parser.add_argument("--trials",type=int,choices=(3,5,7),default=7)
    parser.add_argument("--reference",type=Path,help="Known 6s 1280x720/30fps FFV1/PCM fixture")
    parser.add_argument("--baseline",type=Path,default=BASELINE)
    parser.add_argument("--case",help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.case: return case(json.loads(args.case))
    sys.path.insert(0,str(ROOT))
    from ffv2 import engine
    from ffv2.capabilities import capabilities
    from ffv2.config import Settings,check_mounts
    from ffv2.io import capture,digest,sha256_file,write_json
    directory=Path(str(lab_path('ffmpeg-v2-phase2')))/("benchmark-"+args.mode+"-"+time.strftime("%Y%m%dT%H%M%S",time.gmtime())+"-"+uuid.uuid4().hex[:8])
    check_mounts(directory);directory.mkdir(parents=True)
    source=args.reference or ROOT/".runtime/verification/benchmark-native-20261102T145507-9e28a965/reference.mkv"
    if not source.is_file(): raise RuntimeError("Provide --reference from a completed 6s/720p benchmark fixture")
    selection=None
    if args.mode=="workflow":
        source_selection=engine.selection(verify_hashes=True)
        if set(source_selection["binaries"])!={"ffmpeg","ffprobe"}:
            source_selection={k:v for k,v in source_selection.items() if k!="selection_id"}
            source_selection["binaries"]={k:v for k,v in source_selection["binaries"].items() if k in ("ffmpeg","ffprobe")}
            source_selection["selection_id"]=digest(source_selection)
        selection=directory/"frozen-engine.json";write_json(selection,source_selection)
        configurations={"v0.2.0":{"package":str(args.baseline.resolve()),"selection":str(selection)},
                        "phase2":{"package":str(ROOT),"selection":str(selection)}}
        operations=("transcode","contact_sheet")
        tools={"same_engine":source_selection["binaries"],"selection_id":source_selection["selection_id"]}
    else:
        prefix=args.prefix.resolve(strict=True)
        configurations={"installed":{"package":str(ROOT),"ffmpeg":"/opt/homebrew/bin/ffmpeg","ffprobe":"/opt/homebrew/bin/ffprobe","matched_progress":True},
                        "native":{"package":str(ROOT),"ffmpeg":str(prefix/"bin/ffmpeg"),"ffprobe":str(prefix/"bin/ffprobe"),"matched_progress":True}}
        operations=("software","videotoolbox","contact_sheet")
        tools={name:capabilities(Settings(state=directory/(name+"-state"),ffmpeg=c["ffmpeg"],ffprobe=c["ffprobe"])) for name,c in configurations.items()}
    report={"schema_version":1,"status":"running","directory":str(directory),"mode":args.mode,"trials":args.trials,
            "source":str(source),"source_sha256":sha256_file(source),"binaries":tools,"cases":[],"summary":{},
            "limits":["Busy host, short synthetic 720p/6s fixture; timings do not establish universal speedup.",
                      "One excluded warmup per label/operation; seeded interleaved trial order.",
                      "Full pipeline retains probe, complete decode, hash, atomic publication and resource watchdog.",
                      "Workflow comparison uses the same frozen selected native engine; core comparison uses the same Phase 2 workflow."]}
    if args.mode=="core": report["limits"].append("Both commands use the same legacy key/value progress mode for matched native/installed measurements.")
    def save(): write_json(directory/"report.json",report)
    rng=random.Random(20261102)
    try:
        save()
        for trial in range(args.trials+1):
            pairs=[(label,operation) for label in configurations for operation in operations];rng.shuffle(pairs)
            for label,operation in pairs:
                transcode=operation in ("transcode","software","videotoolbox")
                spec={"operation":"transcode" if transcode else "contact_sheet","input":str(source),
                      "output":str(directory/(label+"-"+operation+"-"+str(trial)+(".mp4" if transcode else ".jpg")))}
                if transcode: spec.update(encoder="videotoolbox" if operation=="videotoolbox" else "software",video_bitrate=4_000_000,rate_control="bitrate",fps=30)
                else: spec.update(count=16,columns=4,max_width=320,max_height=180)
                request={**configurations[label],"state":str(directory/(label+"-state")),"spec":spec,"label":label,"trial":trial,"warmup":trial==0}
                started=time.monotonic()
                child=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),"--case",json.dumps(request)],
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=150)
                if child.returncode: raise RuntimeError(child.stderr[-4000:])
                value=json.loads(child.stdout);value["cli_process_seconds"]=time.monotonic()-started;report["cases"].append(value);save()
        for label in configurations:
            for operation in ("transcode","contact_sheet") if args.mode=="workflow" else operations:
                actual_operation="transcode" if operation in ("software","videotoolbox") else operation
                rows=[r for r in report["cases"] if r["label"]==label and not r["warmup"] and r["operation"]==actual_operation
                      and (operation not in ("software","videotoolbox") or ("-"+operation+"-") in r["output"])]
                summary={"n":len(rows),"output_bytes":sorted({r["bytes"] for r in rows}),"unique_file_hashes":len({r["sha256"] for r in rows})}
                for field in ("capability_seconds","planning_seconds","work_seconds","total_seconds","encode_seconds","decode_seconds","cli_process_seconds"):
                    values=[r[field] for r in rows];summary[field]={"median":statistics.median(values),"min":min(values),"max":max(values)}
                report["summary"][label+"-"+operation]=summary
        if args.mode=="workflow":
            for operation in operations:
                hashes={r["sha256"] for r in report["cases"] if r["operation"]==operation}
                if len(hashes)!=1: raise RuntimeError("Matched workflow outputs differ")
        else:
            from verify_phase2 import Verification
            verify=Verification(args.prefix.resolve(),directory/"quality")
            quality={}
            for label in configurations:
                for encoder in ("software","videotoolbox"):
                    row=next(r for r in report["cases"] if r["label"]==label and ("-"+encoder+"-") in r["output"] and not r["warmup"])
                    metric=verify.directory/(label+"-"+encoder+".json")
                    graph=("[0:v]settb=AVTB,setpts=N/(30*TB)[main];[1:v]settb=AVTB,setpts=N/(30*TB)[ref];"
                           "[main][ref]libvmaf=log_fmt=json:log_path="+str(metric)+":n_threads=2:feature=name=psnr|name=float_ssim:shortest=1")
                    verify.aux("quality-"+label+"-"+encoder,[str(args.prefix/"bin/ffmpeg"),"-v","error","-nostdin","-filter_complex_threads","1",
                        "-threads","2","-i",row["output"],"-threads","2","-i",str(source),"-filter_complex",graph,"-an","-threads","2","-f","null","-"],metric)
                    data=json.loads(metric.read_text())
                    if len(data["frames"])!=180: raise RuntimeError("Expected exactly 180 aligned quality frames")
                    quality[label+"-"+encoder]={"frames":180,"pooled_metrics":data["pooled_metrics"]}
            report["quality"]=quality
        report["status"]="completed";save()
    except BaseException as error:
        report.update(status="failed",error=str(error)[:6000]);save();raise
    print(json.dumps({"status":"completed","report":str(directory/"report.json"),"summary":report["summary"]},ensure_ascii=False))
    return 0


if __name__=="__main__": raise SystemExit(main())
