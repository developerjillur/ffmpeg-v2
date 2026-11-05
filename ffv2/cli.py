from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import __version__
from .benchmark import benchmark
from .capabilities import capabilities, doctor
from .config import Settings
from .errors import FFV2Error
from .io import write_json
from .media import probe
from .planner import build_plan
from .service import submit
from .store import Store
from .worker import work


def read_spec(path):
    path = Path(path)
    if path.stat().st_size > 1024 * 1024:
        raise FFV2Error("spec_too_large", "Job spec সর্বোচ্চ 1 MiB।")
    return json.loads(path.read_text(encoding="utf-8"))


def parser():
    root = argparse.ArgumentParser(prog="ffv2", description="Resource-safe স্থানীয় FFmpeg workflow")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--state-dir", help="Project/NexaWork-এ private runtime directory")
    root.add_argument("--input-root", action="append", help="MCP-এর read allowlist; repeat করা যায়")
    root.add_argument("--ignore-system-memory", action="store_true", help="এই invocation ও workers-এ pressure/headroom/swap stop উপেক্ষা করুন")
    commands = root.add_subparsers(dest="command", required=True)
    doctor_parser = commands.add_parser("doctor", help="Capability ও live resource admission")
    doctor_parser.add_argument("--refresh", action="store_true", help="Verified capability cache পুনরায় probe করুন")
    sub = commands.add_parser("probe", help="Local media metadata")
    sub.add_argument("path")
    for name in ("plan", "submit", "run"):
        sub = commands.add_parser(name, help={"plan": "Job plan দেখুন", "submit": "Job queue করুন", "run": "Queue ও এক job চালান"}[name])
        sub.add_argument("spec")
        if name != "plan":
            sub.add_argument("--key")
    sub = commands.add_parser("worker", help="একটি sequential worker চালান")
    sub.add_argument("--drain", action="store_true", help="সর্বোচ্চ 100টি queued job; resource stop-এ exit")
    sub.add_argument("--job-id")
    sub = commands.add_parser("jobs", help="সাম্প্রতিক job")
    sub.add_argument("--limit", type=int, default=20)
    for name in ("status", "cancel", "retry"):
        sub = commands.add_parser(name)
        sub.add_argument("job_id")
        if name == "status":
            sub.add_argument("--events", action="store_true")
    for name in ("benchmark-plan", "benchmark"):
        sub = commands.add_parser(name, help="Bounded software/VideoToolbox comparison")
        sub.add_argument("input")
        sub.add_argument("--output-dir", required=True)
        sub.add_argument("--seconds", type=int, default=8)
        sub.add_argument("--trials", type=int, default=3)
    commands.add_parser("mcp", help="stdio MCP server; stdout শুধু JSON-RPC")
    sub = commands.add_parser('exec', help='Trusted local consumer-কে pinned FFmpeg PATH ও watchdog দিয়ে চালান')
    sub.add_argument('--work-dir', required=True)
    sub.add_argument('--timeout', type=int, default=1800)
    sub.add_argument('program', nargs=argparse.REMAINDER)
    sub = commands.add_parser('release', help='Frozen code/engine pair install, status ও retained rollback')
    sub.add_argument('action', choices=('status','install','activate','rollback','link-launchers'))
    sub.add_argument('--acceptance')
    sub.add_argument('--source')
    sub.add_argument('--manifest')
    sub = commands.add_parser("engine", help="Verified native build নির্বাচন, inspection অথবা reversible deactivation")
    sub.add_argument("action", choices=("status", "activate", "deactivate"))
    sub.add_argument("--manifest")
    sub.add_argument("--verification")
    sub = commands.add_parser("upstream", help="Locked source fork ও isolated native candidate build")
    sub.add_argument("action", choices=("status", "prepare", "build", "resume"))
    sub.add_argument("--job-id", help="Resume-এর original failed build ID")
    sub.add_argument("--profile", choices=("native", "baseline", "m4"), default="native")
    sub.add_argument("--jobs", type=int, choices=(1, 2), default=2, help="Build/FATE concurrency; 1 কম RAM ব্যবহার করার target")
    sub.add_argument("--plan", action="store_true", help="শুধু source/build plan; heavy কাজ নয়")
    sub.add_argument("--key")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    import os
    previous_memory_override = os.environ.get("FFV2_IGNORE_SYSTEM_MEMORY")
    if args.ignore_system_memory:
        os.environ["FFV2_IGNORE_SYSTEM_MEMORY"] = "1"
    code = 0
    try:
        settings = Settings.load(state=args.state_dir, input_roots=args.input_root, use_active=args.command != "engine")
        if args.command == 'exec':
            from .runtime import run
            command = args.program[1:] if args.program[:1] == ['--'] else args.program
            result = run(settings, command, args.work_dir, timeout=args.timeout)
        elif args.command == 'release':
            from . import releases
            if args.action == 'install':
                if not args.acceptance:
                    raise FFV2Error('release_acceptance_required', '--acceptance প্রয়োজন।')
                result = releases.install(args.acceptance, settings, source=args.source)
            elif args.action == 'activate':
                if not args.manifest:
                    raise FFV2Error('release_manifest_required', '--manifest প্রয়োজন।')
                result = releases.activate_manifest(Path(args.manifest).resolve(strict=True), settings)
            elif args.action == 'rollback':
                result = releases.rollback(settings)
            elif args.action == 'link-launchers':
                result = releases.link_launchers()
            else:
                result = releases.status()
        elif args.command == "engine":
            from . import engine
            if os.environ.get('FFV2_RELEASE_ID') and args.action != 'status':
                raise FFV2Error('release_engine_pinned', 'Installed release-এর engine code-এর সঙ্গে pinned; release install/rollback ব্যবহার করুন।')
            if args.action == "activate":
                if not args.manifest or not args.verification:
                    raise FFV2Error("engine_arguments_required", "--manifest ও --verification প্রয়োজন।")
                result = engine.activate(args.manifest, args.verification)
            else:
                result = engine.status() if args.action == "status" else engine.deactivate()
        elif args.command == "doctor":
            result = doctor(settings, refresh=args.refresh)
        elif args.command == "probe":
            result = probe(args.path, settings, capabilities(settings))
        elif args.command in ("plan", "submit", "run"):
            spec = read_spec(args.spec)
            if args.command == "plan":
                result = build_plan(spec, settings, capabilities(settings))
            else:
                result = submit(spec, settings, key=args.key)
                if args.command == "run" and result["status"] in ("queued", "waiting_resources"):
                    work(settings, job_id=result["id"])
                    result = Store(settings).get(result["id"], plan=False)
        elif args.command == "worker":
            result = work(settings, job_id=args.job_id, drain=args.drain)
        elif args.command == "jobs":
            result = {"jobs": Store(settings).list(args.limit)}
        elif args.command in ("status", "cancel", "retry"):
            store = Store(settings)
            result = {"status": lambda: store.get(args.job_id, plan=False),
                      "cancel": lambda: store.cancel(args.job_id), "retry": lambda: store.retry(args.job_id)}[args.command]()
            if args.command == "status" and args.events:
                result["events"] = store.events(args.job_id)
        elif args.command in ("benchmark-plan", "benchmark"):
            result = benchmark(settings, args.input, args.output_dir, seconds=args.seconds, trials=args.trials,
                               execute=args.command == "benchmark")
        elif args.command == "mcp":
            from .mcp import serve
            serve(settings)
            return 0
        elif args.command == "upstream":
            from .upstream import run
            result = run(settings, args.action, profile=args.profile, plan_only=args.plan, key=args.key, jobs=args.jobs, job_id=args.job_id)
        else:
            raise FFV2Error("unknown_command", "Command পাওয়া যায়নি।")
        if isinstance(result, dict) and args.command in ("run", "worker", "benchmark", "upstream"):
            states = [job["status"] for job in result.get("jobs", [])] if args.command == "worker" else [result.get("status")]
            if any(status in ("waiting_resources", "not_admitted") for status in states):
                code = 75
            elif any(status in ("failed", "interrupted", "incomplete") for status in states):
                code = 1
            elif "cancelled" in states:
                code = 130
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (FFV2Error, OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        if isinstance(error, FFV2Error):
            failure = error
        elif isinstance(error, sqlite3.Error):
            failure = FFV2Error('state_unavailable', 'Queue storage পড়া/লেখা যায়নি; database অক্ষুণ্ণ রেখে inspect করুন।',
                                details={'type':type(error).__name__}, retryable=True, exit_code=75)
        else:
            failure = FFV2Error('invalid_request', 'Command সম্পূর্ণ হয়নি।', details={'type':type(error).__name__, 'message':str(error)[:1000]})
        print(json.dumps({"error": failure.payload()}, ensure_ascii=False, indent=2), file=sys.stderr)
        return failure.exit_code
    except KeyboardInterrupt:
        print(json.dumps({"error": {"code": "interrupted", "message": "কাজ থামানো হয়েছে।"}}, ensure_ascii=False), file=sys.stderr)
        return 130
    finally:
        if args.ignore_system_memory:
            if previous_memory_override is None:
                os.environ.pop("FFV2_IGNORE_SYSTEM_MEMORY", None)
            else:
                os.environ["FFV2_IGNORE_SYSTEM_MEMORY"] = previous_memory_override


if __name__ == "__main__":
    raise SystemExit(main())
