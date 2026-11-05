from __future__ import annotations

import json
import sqlite3
import sys

from . import __version__
from .capabilities import capabilities, doctor
from .errors import FFV2Error
from .media import probe
from .planner import SPEC_SCHEMA, build_plan
from .service import start_worker, submit
from .store import Store

VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
EMPTY = {"type": "object", "properties": {}, "additionalProperties": False}
JOB = {"type": "object", "properties": {"job_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"}}, "required": ["job_id"], "additionalProperties": False}


def tool(name, description, schema, *, read_only=True, idempotent=True):
    return {"name": name, "description": description, "inputSchema": schema, "outputSchema": {"type": "object"},
            "annotations": {"readOnlyHint": read_only, "destructiveHint": False,
                            "idempotentHint": idempotent, "openWorldHint": False}}


TOOLS = [
    tool("ffv2_doctor", "Installed FFmpeg, listed hardware capabilities ও live resource admission দেখুন। Encoding চালায় না।", EMPTY),
    tool("ffv2_probe", "অনুমোদিত local input-এর bounded metadata পড়ুন।", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}),
    tool("ffv2_plan", "Typed media job-এর exact argv, expected output, resource estimate ও warning দেখুন।", {"type": "object", "properties": {"spec": SPEC_SCHEMA}, "required": ["spec"], "additionalProperties": False}),
    tool("ffv2_submit", "Idempotent media job queue করুন। Worker আলাদাভাবে শুরু করতে হয়।", {"type": "object", "properties": {"spec": SPEC_SCHEMA, "idempotency_key": {"type": "string"}}, "required": ["spec"], "additionalProperties": False}, read_only=False),
    tool("ffv2_worker_start", "User-requested queued media jobs-এর resource-guarded sequential worker শুরু করুন; status poll করুন।", {"type": "object", "properties": {"ignore_system_memory": {"type": "boolean"}}, "additionalProperties": False}, read_only=False, idempotent=False),
    tool("ffv2_job_status", "Job status, progress, typed error ও verification receipt পড়ুন।", JOB),
    tool("ffv2_job_cancel", "নির্দিষ্ট job বাতিল করুন; তার process-ই থামবে, partial রাখা হবে।", JOB, read_only=False),
    tool("ffv2_job_retry", "Failed/stopped job নতুন attempt-এ queue করুন; পুরোনো partial অক্ষুণ্ণ থাকবে।", JOB, read_only=False, idempotent=False),
]


def arguments(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise FFV2Error("invalid_arguments", "Tool-এর required/allowed field ঠিক করুন।")
    return value


def call(name, args, settings):
    if name not in ('ffv2_doctor','ffv2_job_status','ffv2_job_cancel'):
        from .releases import assert_current
        assert_current()
    if name == "ffv2_doctor":
        arguments(args, ())
        return doctor(settings)
    if name == "ffv2_probe":
        arguments(args, ("path",), ("path",))
        return probe(args["path"], settings, capabilities(settings), restricted=True)
    if name in ("ffv2_plan", "ffv2_submit"):
        arguments(args, ("spec",) if name == "ffv2_plan" else ("spec", "idempotency_key"), ("spec",))
        if name == "ffv2_plan":
            return build_plan(args["spec"], settings, capabilities(settings), restricted=True)
        return submit(args["spec"], settings, key=args.get("idempotency_key"), restricted=True)
    if name == "ffv2_worker_start":
        arguments(args, ('ignore_system_memory',))
        if type(args.get('ignore_system_memory', False)) is not bool:
            raise FFV2Error('invalid_arguments', 'ignore_system_memory boolean হতে হবে।')
        return start_worker(settings, ignore_system_memory=args.get('ignore_system_memory', False))
    if name in ("ffv2_job_status", "ffv2_job_cancel", "ffv2_job_retry"):
        arguments(args, ("job_id",), ("job_id",))
        store = Store(settings)
        return {"ffv2_job_status": lambda: store.get(args["job_id"], plan=False),
                "ffv2_job_cancel": lambda: store.cancel(args["job_id"]),
                "ffv2_job_retry": lambda: store.retry(args["job_id"])}[name]()
    raise FFV2Error("tool_not_found", "Tool পাওয়া যায়নি।")


class Server:
    def __init__(self, settings):
        from .bindings import workflow_identity
        self.settings = settings
        self.runtime_code_id = workflow_identity()
        self.initialized = False
        self.ready = False

    def handle(self, message):
        identity = message.get("id") if isinstance(message, dict) else None
        def error(code, text):
            return {"jsonrpc": "2.0", "id": identity, "error": {"code": code, "message": text}}
        if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or
                not isinstance(message.get("method"), str) or
                ("id" in message and (type(identity) not in (int, str) and identity is not None))):
            return error(-32600, "Invalid Request")
        method, params = message["method"], message.get("params", {})
        if not isinstance(params, dict):
            return error(-32602, "Invalid params") if "id" in message else None
        if "id" not in message:
            if method == "notifications/initialized" and self.initialized:
                self.ready = True
            return None
        if method == "initialize":
            if self.initialized or not isinstance(params.get("protocolVersion"), str):
                return error(-32602, "Invalid initialization")
            self.initialized = True
            version = params["protocolVersion"] if params["protocolVersion"] in VERSIONS else VERSIONS[-1]
            result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "ffmpeg-v2", "title": "FFmpeg-v2", "version": __version__},
                      "instructions": "Local files only. Plan, submit, explicitly start worker, poll status. Hardware listing is not runtime verification."}
        elif method == "ping":
            result = {}
        elif not self.ready:
            return error(-32002, "Server not initialized")
        elif method == "tools/list":
            if params.get("cursor"):
                return error(-32602, "Invalid cursor")
            result = {"tools": TOOLS}
        elif method == "tools/call":
            if not isinstance(params.get("name"), str):
                return error(-32602, "Tool name required")
            if params["name"] not in {t["name"] for t in TOOLS}:
                return error(-32602, "Unknown tool")
            try:
                if params['name'] not in ('ffv2_doctor', 'ffv2_job_status', 'ffv2_job_cancel'):
                    from .bindings import assert_workflow
                    assert_workflow({'runtime_code_id': self.runtime_code_id})
                value = call(params["name"], params.get("arguments", {}), self.settings)
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False, allow_nan=False)}],
                          "structuredContent": value, "isError": False}
            except (FFV2Error, OSError, ValueError, TypeError, sqlite3.Error) as caught:
                if isinstance(caught, FFV2Error):
                    failure = caught
                elif isinstance(caught, sqlite3.Error):
                    failure = FFV2Error('state_unavailable', 'Queue storage unavailable; database অক্ষুণ্ণ আছে।',
                                        details={'type':type(caught).__name__}, retryable=True, exit_code=75)
                else:
                    failure = FFV2Error('tool_error', 'Tool সম্পূর্ণ হয়নি।', details={'type':type(caught).__name__})
                result = {"content": [{"type": "text", "text": json.dumps(failure.payload(), ensure_ascii=False)}], "isError": True}
        else:
            return error(-32601, "Method not found")
        return {"jsonrpc": "2.0", "id": identity, "result": result}


def serve(settings, source=None, target=None):
    source = source or sys.stdin.buffer
    target = target or sys.stdout
    server = Server(settings)
    limit = 1024 * 1024
    while True:
        raw = source.readline(limit + 1)
        if not raw:
            break
        if len(raw) > limit:
            while raw and not raw.endswith(b"\n"):
                raw = source.readline(limit + 1)
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Message too large"}}
        else:
            try:
                message = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                response = server.handle(message)
            except (ValueError, UnicodeDecodeError):
                response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        if response is not None:
            target.write(json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n")
            target.flush()
