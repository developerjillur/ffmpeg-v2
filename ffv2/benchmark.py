from __future__ import annotations

import random
import statistics
import os
import uuid
from pathlib import Path

from .capabilities import capabilities
from .errors import FFV2Error
from .io import digest, output_path, write_json
from .media import probe
from .planner import build_plan
from .resources import Policy, snapshot
from .store import Store
from .worker import work


def benchmark(settings, input_file, output_dir, *, seconds=8, trials=3, execute=False):
    if type(seconds) is not int or not 1 <= seconds <= 30 or type(trials) is not int or not 1 <= trials <= 5:
        raise FFV2Error("invalid_benchmark", "Benchmark 1–30 সেকেন্ড এবং 1–5 trial-এর মধ্যে রাখুন।")
    caps = capabilities(settings)
    source = probe(input_file, settings, caps)
    if not source["video"]:
        raise FFV2Error("video_missing", "Encoder comparison-এর জন্য video input দিন।")
    target = Path(output_dir).absolute().resolve()
    if not target.is_dir():
        raise FFV2Error("output_directory_missing", "Benchmark-এর output directory আগে তৈরি করুন।")
    output_path(str(target / "benchmark.json"), Path(source["path"]), settings)
    duration = min(seconds, source["duration_seconds"])
    token = digest({"source": source["fingerprint"], "path": source["path"], "duration": duration, "trials": trials})[:12]
    report_path = target / ("benchmark-" + token + ".json")
    output_path(str(report_path), Path(source["path"]), settings)
    order = [(encoder, trial) for trial in range(1, trials + 1) for encoder in ("software", "videotoolbox")]
    random.Random(0).shuffle(order)
    specs = [{"operation": "transcode", "input": source["path"],
              "output": str(target / f"{token}-{encoder}-{trial}.mp4"),
              "encoder": encoder, "max_width": 1280, "max_height": 720, "fps": 30,
              "duration": duration, "video_bitrate": 4_000_000, "rate_control": "bitrate", "threads": 2}
             for encoder, trial in order]
    report = {"schema_version": 1, "status": "planned", "source": source, "duration_seconds": duration,
              "seed": 0, "order": order, "warmup": "none; first-run overhead retained",
              "binary": {k: caps[k] for k in ("ffmpeg", "ffmpeg_version", "ffmpeg_identity")},
              "specs": specs, "results": [], "quality_parity": "not_measured",
              "limits": ["Same target bitrate/resolution/fps does not establish equal visual quality.",
                         "Synthetic/short segment throughput does not establish long-form or all-workload speedup.",
                         "Validation time is reported separately; no result is a core-patch speedup claim."]}
    if not execute:
        return report
    sample = snapshot(target)
    reasons = Policy().admission(sample, 2 * 1024 ** 3, len(specs) * 128 * 1024 ** 2)
    if reasons:
        report.update(status="not_admitted", admission_reasons=reasons, resources=sample.json())
        return report
    store = Store(settings)
    for (encoder, trial), spec in zip(order, specs):
        plan = build_plan(spec, settings, caps)
        job = store.enqueue(plan)
        work(settings, job_id=job["id"])
        result = store.get(job["id"], plan=False)
        receipt = result.get("receipt") or {}
        report["results"].append({"encoder": encoder, "trial": trial, "job_id": job["id"], "status": result["status"],
                                   "encode_wall_seconds": receipt.get("encode_wall_seconds"),
                                   "validation_wall_seconds": receipt.get("validation_wall_seconds"),
                                   "output_bytes": receipt.get("output_bytes"), "output_sha256": receipt.get("output_sha256")})
        if result["status"] != "completed":
            report["status"] = "incomplete"
            break
    else:
        report["status"] = "completed"
        medians = {encoder: statistics.median(r["encode_wall_seconds"] for r in report["results"] if r["encoder"] == encoder)
                   for encoder in ("software", "videotoolbox")}
        report["median_encode_wall_seconds"] = medians
        report["software_over_videotoolbox_time_ratio"] = medians["software"] / medians["videotoolbox"]
    temporary = target / (".benchmark-" + uuid.uuid4().hex + ".json")
    write_json(temporary, report)
    os.link(temporary, report_path, follow_symlinks=False)
    report["report_path"] = str(report_path)
    return report
