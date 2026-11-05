# FFmpeg MCP server

FFmpeg-v2 exposes local media workflows through stdio MCP. It accepts one JSON-RPC
message per line and reserves stdout for protocol messages. There is no HTTP
listener, provider login or cloud upload. Only local allowed paths are accepted.

## Generate configuration

Install the [source checkout](GETTING-STARTED.md), then run:

```sh
.venv/bin/python scripts/configure_local_mcp.py \
  --project /absolute/path/to/media-project \
  --work-root /absolute/path/to/workspace \
  --command /absolute/path/to/ffmpeg-v2/.venv/bin/ffv2
```

The script prints a client-neutral JSON configuration and does not edit your
settings. Use an existing media-project directory and absolute executable paths.
Copy the mcpServers entry into your client's supported configuration format.
Client UIs and file locations vary; restart the connection after changing it.

```json
{
  "mcpServers": {
    "ffmpeg-v2": {
      "command": "/absolute/path/to/ffmpeg-v2/.venv/bin/ffv2",
      "args": ["--input-root", "/absolute/path/to/media-project", "mcp"],
      "env": {
        "FFV2_PROJECT_ROOT": "/absolute/path/to/media-project",
        "FFV2_WORK_ROOT": "/absolute/path/to/workspace"
      }
    }
  }
}
```

## Eight tools and their boundaries

| Tool | Effect |
|---|---|
| ffv2_doctor | Inspect capabilities and live admission. Read-only media behavior. |
| ffv2_probe | Read bounded metadata from an allowed local input. |
| ffv2_plan | Inspect typed argv, estimates and warnings. No encode. |
| ffv2_submit | Queue an idempotent typed media job. No automatic worker. |
| ffv2_worker_start | Explicitly start a supervised sequential worker. |
| ffv2_job_status | Read status, progress and verification receipt. |
| ffv2_job_cancel | Cancel the specified job, preserving its evidence. |
| ffv2_job_retry | Queue a new attempt for a failed/stopped job. |

Read-only planning may create bounded capability/runtime caches. Restrict the input
root to files you intend the client to read. A safe interaction is **plan → inspect
→ submit → explicitly start worker → poll until completed**. Launch success and
progress=end are not output acceptance. Review failed/resource-stop reasons.
Arbitrary shell/raw argv and native release promotion are not MCP tools.

Protocol versions recognized: 2024-11-05, 2025-03-26, 2025-06-18 and 2025-11-25.
Initialize first, send notifications/initialized, then tools/list or tools/call.
The server uses line-delimited JSON, not Content-Length framing. Supported client
features must be verified in that client's actual connection. A source or engine
change invalidates existing workflow identity; reconnect on release_changed.

[Technical historical MCP contract](MCP.md) · [Configuration](CONFIGURATION.md) ·
[Python integration](PYTHON.md) · [Security](../SECURITY.md)
