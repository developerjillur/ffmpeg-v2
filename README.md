<p align="center"><img src="site/assets/mark.svg" width="64" height="64" alt="FFmpeg-v2 workflow mark"></p>

# FFmpeg-v2 · verified local media workflows

**Typed FFmpeg jobs, a resource-aware CLI and an MCP server for macOS.** Plan the
work, run it under supervision, verify the output, then publish it without
overwriting an existing file.

[![Source CI](https://github.com/developerjillur/ffmpeg-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/developerjillur/ffmpeg-v2/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-2f5c43)](https://developerjillur.github.io/ffmpeg-v2/)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](pyproject.toml)

[**Documentation**](https://developerjillur.github.io/ffmpeg-v2/) ·
[Quick start](docs/GETTING-STARTED.md) · [CLI](docs/CLI.md) · [MCP](docs/MCP-PUBLIC.md) ·
[Benchmark explorer](https://developerjillur.github.io/ffmpeg-v2/benchmarks/) ·
[All reports](docs/REPORTS.md) · [বাংলা historical overview](README.bn.md)

Maintained by **Jillur Rahman**. Independent of the FFmpeg project. This repository
contains a workflow toolkit and optional native patch sets; it is not an official
FFmpeg successor or a claim that every encode is faster than Stock FFmpeg.

## What you can build

- Local transcription preparation: extract bounded mono PCM audio and frame samples.
- Application pipelines: transcode, remux, sample frames/contact sheets, concatenate,
  burn subtitles, mix audio, convert images and apply explicit HDR/interlace policies.
- MCP integrations: eight typed tools for planning, queueing, starting a worker,
  polling, cancelling and retrying. Local files only; no arbitrary shell tool.
- Inspectable execution: exact argv, source/binary fingerprints, idempotency keys,
  SQLite history, progress events and structured error codes.
- Guarded output: sequential worker, independent watchdog, timeout/resource checks,
  full decode and metadata validation, SHA-256, staging and no-clobber publication.
- Native research: checksum-pinned FFmpeg patches for JSONL progress and Metal
  runtime/lifetime fixes; experimental x264 progress/PGO work with honest outcomes.

## Quick start

Supported execution target: **macOS, tested on Apple Silicon**. Python 3.9+ and
FFmpeg/FFprobe on PATH are required. Linux/Windows supervision and GPU support are
not verified. Start from a source checkout; native build/release commands also need
the repository's patch and lock files.

```sh
git clone https://github.com/developerjillur/ffmpeg-v2.git
cd ffmpeg-v2
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
# Install FFmpeg separately if it is missing, e.g. brew install ffmpeg
.venv/bin/ffv2 --version
```

Use a dedicated media workspace. The input and new output must be inside its
allowed roots. These commands do not replace system FFmpeg or activate a native
candidate.

```sh
mkdir -p media-project
export FFV2_PROJECT_ROOT="$PWD/media-project"
export FFV2_WORK_ROOT="$FFV2_PROJECT_ROOT/.ffv2-work"
.venv/bin/ffv2 doctor
# Place a local input.mp4 in media-project, then:
cat > media-project/job.json <<'JSON'
{
  "operation": "audio",
  "input": "input.mp4",
  "output": "voice.wav",
  "audio_rate": 16000,
  "audio_channels": 1,
  "threads": 2
}
JSON
# Paths inside a spec resolve from the command's working directory.
(cd media-project && ../.venv/bin/ffv2 plan job.json)
(cd media-project && ../.venv/bin/ffv2 run job.json)
```

`plan` inspects media but does not encode. `submit` only queues; `worker` starts
execution. `run` queues and runs one job. A completed receipt confirms validation
and publication; `progress=end` alone does not. See [configuration](docs/CONFIGURATION.md)
if resource admission asks you to wait or if media lives on an external volume.

## Performance: what the evidence actually supports

The experimental Phase 11 PGO candidate matched decoded video/audio and quality
metrics. The complete 1080p workflow was faster in one bounded M4 Max experiment;
the direct encoder sample requirement failed. **The candidate was not promoted.**

| Phase 11 workload vs Stock | Valid blocks / required | Paired elapsed change | 95% ratio interval | Decision |
|---|---:|---:|---|---|
| Complete HD workflow, load0 | 9 / 9 | −1.743% | 0.9799–0.9853 | Pass for this workload |
| Complete HD workflow, load2 | 9 / 9 | −1.791% | 0.9797–0.9849 | Pass for this workload |
| Direct HD, load0 / load2 | 1 / 9 each | Insufficient | Not estimated | Fail sample gate |
| Direct raw, load0 | 3 / 9 | −1.801% observed | 0.9780–0.9844 | Insufficient release proof |
| Direct raw, load2 | 7 / 9 | −1.994% observed | 0.9773–0.9829 | Insufficient release proof |

Negative change means less elapsed time. Changes are geometric means of paired
block ratios, not ratios of displayed medians. load2 adds two 50%-duty CPU helpers;
other host activity was observed and gated. Warmups/rejected blocks are excluded
from accepted timing. Full method, both original-native and Stock comparisons,
quality tables and failed experiments: [English benchmark guide](docs/BENCHMARKS.md),
[Phase 11 report](docs/PHASE11-RESULTS.md), [machine-readable analyses](docs/benchmarks/).

Earlier Phase 8 tuning reduced complete-workflow time 22.31% / 30.77% versus the
old native workflow on two sources. Those are different experiments and references;
they are **not** a universal or same-tuning encoder speed claim. See the [complete
archive](docs/REPORTS.md), including regressions and rejected candidates.

## Connect an MCP client

```sh
.venv/bin/python scripts/configure_local_mcp.py \
  --project "$FFV2_PROJECT_ROOT" --command "$PWD/.venv/bin/ffv2"
```

This prints configuration; it does not edit any client's settings. Copy the result
into a compatible stdio MCP client and restart that connection. Read [MCP setup,
permissions and protocol](docs/MCP-PUBLIC.md). No provider account or hosted API is
needed. [Python integration](docs/PYTHON.md) uses the same typed planner and queue.

## Status and boundaries

Public source version **0.6.1** adds portable workspace configuration, public docs
and publication checks. It does not promote the experimental PGO engine. No native
binaries, media corpus, private profiles, runtime databases or owner-specific
release installations are bundled. Historical reports and redacted evidence indexes
are included; their private paths are placeholders, not executable local receipts.
Some historical/runtime diagnostics remain in Bengali; stable error codes and the
new guides are in English.

Run the source suite with `python3 -B -W error::ResourceWarning -m unittest discover
-s tests -v`. [Source CI](https://github.com/developerjillur/ffmpeg-v2/actions/workflows/ci.yml)
checks behavior; it does not reproduce the native performance experiment. See
[known limitations](docs/LIMITATIONS.md), [contributing](CONTRIBUTING.md),
[security](SECURITY.md), [release notes](CHANGELOG.md) and [citation](CITATION.cff).

[Publication/evidence policy](docs/PUBLICATION.md) · [Open roadmap](docs/ROADMAP.md) ·
[Discovery and sharing](docs/DISCOVERY.md)

## License and upstream

Toolkit: [GPL-3.0-or-later](LICENSE). FFmpeg and dependency notices stay with their
respective sources; [third-party notices](THIRD-PARTY-NOTICES.md) and exact
[upstream lock](upstream.lock.json) describe the optional source builds. This is a
source-only publication, not a binary redistribution of a locally linked engine.
Review the applicable licenses when distributing your own built application.
