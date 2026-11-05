# Python integration

Use the same typed planner and queue from your local application. Install from a
source checkout in your application's environment. Set workspace environment
variables **before importing ffv2**, because configuration is loaded per process.
This is a small local Python API; version your integration and use the documented
CLI/MCP contracts when you need process isolation.

```python
import os
os.environ["FFV2_PROJECT_ROOT"] = "/absolute/path/to/media-project"

from ffv2.config import Settings
from ffv2.capabilities import capabilities
from ffv2.planner import build_plan
from ffv2.service import submit
from ffv2.worker import work
from ffv2.store import Store

settings = Settings.load()
spec = {
    "operation": "audio",
    "input": "/absolute/path/to/media-project/input.mp4",
    "output": "/absolute/path/to/media-project/speech.wav",
    "audio_rate": 16000,
    "audio_channels": 1,
    "threads": 2,
}
plan = build_plan(spec, settings, capabilities(settings), restricted=True)
print(plan)  # Inspect before submission.
job = submit(spec, settings, key="speech-001", restricted=True)
# Run this in your application's background worker, not its UI thread.
work(settings, job_id=job["id"])
result = Store(settings).get(job["id"])
assert result["status"] == "completed", result
```

The example performs real local work when run. Use an existing input and a fresh
output path. The queue validates changed source/backend identity again at execution.
An idempotency key identifies the same plan, not permission to overwrite results.
Cancellation and recovery operate on owned processes only. Exceptions contain
stable FFV2Error codes; inspect job events and retained receipts on failure.

[CLI integration](CLI.md) · [MCP integration](MCP-PUBLIC.md) ·
[Architecture](ARCHITECTURE.md) · [Configuration](CONFIGURATION.md)
