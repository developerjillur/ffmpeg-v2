#!/usr/bin/python3 -B
"""Candidate ও completed reports থেকে local Phase 2 acceptance index তৈরি।"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ffv2.engine import PHASE2_REQUIRED, library_closure, verify_extended
from ffv2.io import sha256_file, write_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",required=True,type=Path)
    parser.add_argument("--native",required=True,type=Path)
    parser.add_argument("--report",required=True,action="append",type=Path)
    parser.add_argument("--workflow",required=True,type=Path)
    parser.add_argument("--core",required=True,type=Path)
    args=parser.parse_args()
    candidate=json.loads(args.manifest.read_text());native=json.loads(args.native.read_text())
    prefix=Path(candidate["install_prefix"])
    if native["status"]!="completed" or native["install_prefix"]!=str(prefix): raise RuntimeError("Native media proof does not match candidate")
    programs=[prefix/"bin"/name for name in candidate["binaries"]]
    if native["verified_files"]!=library_closure(programs): raise RuntimeError("Verified binary/library set changed")
    index={"schema_version":1,"status":"completed","maintainer":"Jillur Rahman","created_at":time.time(),
           "install_prefix":str(prefix),"binary_version":native["binary_version"],"source":candidate["source"],
           "candidate":{"path":str(args.manifest.resolve()),"sha256":sha256_file(args.manifest)},"reports":[],"tests":{},
           "runtime_code_sha256":{str(p.relative_to(ROOT)):sha256_file(p) for p in sorted((ROOT/"ffv2").glob("*.py"))}}
    for path in args.report:
        path=path.resolve(strict=True);report=json.loads(path.read_text())
        if report["status"]!="completed" or report["install_prefix"]!=str(prefix) or report["binary_version"]!=native["binary_version"]:
            raise RuntimeError("Extended proof does not match candidate: "+str(path))
        for name,result in report["tests"].items():
            if name in index["tests"] and index["tests"][name]!=result: raise RuntimeError("Conflicting test proof")
            index["tests"][name]=result
        index["reports"].append({"path":str(path),"sha256":sha256_file(path)})
    if any(index["tests"].get(k,{}).get("status")!="pass" for k in PHASE2_REQUIRED): raise RuntimeError("Incomplete Phase 2 acceptance")
    for label,path in (("workflow",args.workflow),("core",args.core)):
        report=json.loads(path.read_text())
        if report["status"]!="completed" or report["mode"]!=label: raise RuntimeError("Incomplete matched benchmark")
        index[label+"_benchmark"]={"path":str(path.resolve()),"sha256":sha256_file(path),"summary":report["summary"]}
    index["core_benchmark"]["quality"]=json.loads(args.core.read_text())["quality"]
    output=args.native.parent/"phase2-acceptance.json"
    if output.exists(): raise RuntimeError("Existing acceptance index preserved; choose a fresh native report")
    write_json(output,index)
    native["phase2_acceptance"]={"path":str(output),"sha256":sha256_file(output)}
    verify_extended(native,prefix)
    write_json(args.native,native)
    portable={k:v for k,v in index.items() if k not in ("runtime_code_sha256",)}
    portable["native_report"]={"path":str(args.native.resolve()),"sha256":sha256_file(args.native)}
    portable["verified_runtime_files"]=len(native["verified_files"])
    fate_dir=prefix.parent/"build/tests/data/fate"
    records=list(fate_dir.glob("*.rep"))
    failures=[p.name for p in records if p.read_text().split(":")[1]!="0"]
    if failures: raise RuntimeError("Nonzero FATE record present")
    portable["fate"]={"records":len(records),"failures":failures,"listed":candidate["fate_list_observed_count"],
                       "scope":candidate["fate_scope"]}
    destination=ROOT/"docs/verification"/("phase2-"+datetime.date.today().isoformat()+".json")
    write_json(destination,portable)
    print(json.dumps({"status":"completed","index":str(output),"portable_receipt":str(destination),"tests":len(index["tests"]),"fate":portable["fate"]},ensure_ascii=False))
    return 0


if __name__=="__main__": raise SystemExit(main())
