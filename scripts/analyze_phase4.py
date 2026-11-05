#!/usr/bin/python3 -B
"""Timing ও all-frame quality-এর predeclared promotion gates।"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.io import sha256_file, write_json


def analyze(report):
    if report["status"] != "completed":
        raise RuntimeError("Only completed timing and quality reports can be promoted")
    threshold = report["quality_thresholds"]
    comparisons = {}
    labels = list(report["configurations"])
    for profile in report["profiles"]:
        pairs = [(labels[0], label, "workflow") for label in labels[1:]]
        if len(labels) == 3 and labels[-1].endswith("stock"):
            pairs.append((labels[-1], labels[1], "engine"))
        for baseline, candidate, kind in pairs:
            base_quality = report["quality"][profile + "/" + baseline]
            a = {r["trial"]: r for r in report["cases"] if r["profile"] == profile and r["label"] == baseline and not r["warmup"]}
            b = {r["trial"]: r for r in report["cases"] if r["profile"] == profile and r["label"] == candidate and not r["warmup"]}
            if set(a) != set(b) or len(a) < 3:
                raise RuntimeError("Expected at least three matched trial blocks")
            quality = report["quality"][profile + "/" + candidate]
            if quality["frames"] != base_quality["frames"] or quality["frames"] != report["seconds"] * report["profiles"][profile].get("fps", 30):
                raise RuntimeError("All-frame quality coverage mismatch")
            deltas = {name: quality["metrics"][key]["mean"] - base_quality["metrics"][key]["mean"]
                      for name, key in (("vmaf", "vmaf"), ("psnr_y", "psnr_y"), ("ssim", "float_ssim"))}
            size_ratio = statistics.median(r["bytes"] for r in b.values()) / statistics.median(r["bytes"] for r in a.values())
            rng, boot = random.Random(20261103), []
            for _ in range(3000):
                sample = rng.choices(sorted(a), k=len(a))
                boot.append(statistics.median(b[i]["total_seconds"] for i in sample) / statistics.median(a[i]["total_seconds"] for i in sample))
            boot.sort()
            ratio = statistics.median(r["total_seconds"] for r in b.values()) / statistics.median(r["total_seconds"] for r in a.values())
            gates = {"vmaf": deltas["vmaf"] >= threshold["vmaf_delta_min"],
                     "psnr_y": deltas["psnr_y"] >= threshold["psnr_y_delta_min"],
                     "ssim": deltas["ssim"] >= threshold["ssim_delta_min"],
                     "size": size_ratio <= threshold["size_ratio_max"],
                     "median_faster": ratio < 1, "paired_bootstrap_faster": boot[2924] < 1}
            key = profile + "/" + (candidate if kind == "workflow" else "native_vs_stock")
            comparisons[key] = {"baseline": baseline, "candidate": candidate, "comparison_kind": kind, "n_pairs": len(a),
                "quality_frames": quality["frames"], "quality_deltas": deltas, "size_ratio": size_ratio,
                "time_ratio": ratio, "time_reduction_percent": (1 - ratio) * 100,
                "paired_bootstrap_ratio_95_percent": [boot[75], boot[2924]], "gates": gates,
                "promotion_allowed": all(gates.values())}
    return comparisons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    value = {"status": "completed", "source_report": str(args.report), "source_sha256": sha256_file(args.report),
             "comparisons": analyze(report)}
    target = args.report.with_name("analysis.json")
    if target.exists():
        raise RuntimeError("Analysis exists; retain original result")
    write_json(target, value)
    print(json.dumps({"analysis": str(target), "comparisons": value["comparisons"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
