<p align="center"><img src="site/assets/mark.svg" width="64" height="64" alt="FFmpeg-v2 workflow mark"></p>

# FFmpeg-v2 · Faster workflows. Verified outputs.

**Get more from FFmpeg with tuned media workflows, a typed CLI, local MCP tools
and verified results.** Build repeatable video, audio and frame-processing jobs
with a durable queue, resource supervision and an output receipt.

[![Source CI](https://github.com/developerjillur/ffmpeg-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/developerjillur/ffmpeg-v2/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-GitHub%20Pages-2f5c43)](https://developerjillur.github.io/ffmpeg-v2/)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)](pyproject.toml)

[**Why use FFmpeg-v2**](https://developerjillur.github.io/ffmpeg-v2/why-ffmpeg-v2/) ·
[Get started](docs/GETTING-STARTED.md) · [Measured results](https://developerjillur.github.io/ffmpeg-v2/benchmarks/) ·
[CLI](docs/CLI.md) · [MCP](docs/MCP-PUBLIC.md) · [Python](docs/PYTHON.md)

Maintained by **Jillur Rahman**. An independent toolkit built around FFmpeg, with
optional native patches and a tested M4 Max profile. Execution target: macOS / Apple Silicon.

## How much improvement?

**22.61% less HD workflow time and 28.48% less live-action workflow time** in
recorded M4 Max native-profile tests versus the **prior Stock workflow preset**.
Quality gates passed, including full-frame VMAF/PSNR/SSIM checks and full decode.

| 60-second source range | Stock prior preset | FFmpeg-v2 native profile | Less elapsed time | Quality |
|---|---:|---:|---:|---|
| 1080p animation · 1920×1080 / 30fps | 9.7344 s | 7.5339 s | **22.61%** | Passed · 1,800 frames |
| Live action / VFX · 1920×800 / 24fps | 7.5278 s | 5.3840 s | **28.48%** | Passed · 1,440 frames |

**Baseline:** Stock FFmpeg 9.0.2 using encoder/decoder/filter/validation pools
4/2/2/4 versus the tuned native profile's 8/2/2/8; nine measured trials per
configuration, same source range, libx264 veryfast/CRF20 and AAC160k. Both comparators used the same queue and full-validation contract. These are
complete workflow times, not a universal encoder score or an out-of-the-box Stock
default comparison. The native engine is an optional source build.

The gain comes from coordinating encoding and validation pools for eligible
workloads. Stock accepts the same thread controls. [Same-tuning controls and exact
confidence intervals](https://developerjillur.github.io/ffmpeg-v2/benchmarks/#same-tuning)
remain visible: a general native-encoder advantage is not established. Against
the earlier FFmpeg-v2 workflow, the two reductions were **22.31% / 30.77%**.

No configured quality/bitrate reduction was used to get the result. VMAF moved
from 94.761184 to 94.781527 on HD and 93.375096 to 93.379144 on live action;
output sizes increased slightly (+0.162% / +0.024%). [Results, conditions and
quality data](docs/WORKFLOW-RESULTS.md) · [Summary JSON](docs/benchmarks/released-workflow-summary.json).

## Why use it in your project?

- **Use a tested tuning policy.** Eligible long M4 Max software transcodes receive
  coordinated encoder, decoder, filter and validation pools. Other workloads use
  conservative policies; your explicit thread choices remain available.
- **Build around a stable job contract.** Typed JSON becomes an inspectable plan
  with exact argv, resource estimates and source/backend identity checks.
- **Run batches with history.** SQLite queue, idempotency keys, priority,
  cancellation, retry and retained partials make local work recoverable.
- **Accept a verified output.** Metadata, full decode and SHA-256 checks happen
  before staged no-clobber publication; an encode's progress=end is not acceptance.
- **Protect the surrounding application.** An independent supervisor checks owned
  processes, memory pressure, disk space, timeouts and cancellation.
- **Connect MCP and Python directly.** Eight local-file MCP tools and reusable
  Python interfaces expose the same planner, queue and verification contract.
- **Use optional native extensions.** The pinned source patch set adds versioned
  JSONL progress, optional Metal runtime compilation and Metal object-lifetime fixes.

Stock FFmpeg already supplies excellent codecs, filters, thread controls,
progress output, hash formats and overwrite refusal. FFmpeg-v2 packages those
building blocks into a managed application workflow. [Side-by-side product
comparison](docs/WHY-FFMPEG-V2.md).

## What can you build?

| Use case | Included workflow |
|---|---|
| Transcription and media search | Bounded mono PCM extraction, timestamped frames and contact sheets |
| Local editing/export automation | Transcode, remux, compatible concat or explicit normalization, subtitles and audio mixing |
| Application backends | Durable media jobs with progress, cancellation, retry and verification receipts |
| MCP-connected tools | Plan → submit → explicitly start a worker → poll for the verified output |

See [job examples](examples/) and the [CLI reference](docs/CLI.md) for the nine
typed operations and their supported boundaries.

## Start using FFmpeg-v2

Python 3.9+ and FFmpeg/FFprobe on PATH are required. FFmpeg is installed separately;
normal typed workflows can use that existing backend. Native builds need the full
source checkout and fresh local acceptance evidence.

```sh
git clone https://github.com/developerjillur/ffmpeg-v2.git
cd ffmpeg-v2
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/ffv2 --version
mkdir -p media-project
export FFV2_PROJECT_ROOT="$PWD/media-project"
export FFV2_WORK_ROOT="$FFV2_PROJECT_ROOT/.ffv2-work"
.venv/bin/ffv2 doctor
```

Then follow the [five-second job walkthrough](docs/GETTING-STARTED.md). Review a
plan before execution and use a new output path. macOS/Apple Silicon is the
verified execution target; Linux/Windows supervision is not certified.

For an MCP client, print configuration without editing its settings:

```sh
.venv/bin/python scripts/configure_local_mcp.py \
  --project "$FFV2_PROJECT_ROOT" --command "$PWD/.venv/bin/ffv2"
```

[MCP setup](docs/MCP-PUBLIC.md) · [Python integration](docs/PYTHON.md) ·
[Configuration and resource budgets](docs/CONFIGURATION.md) · [Native builds](docs/NATIVE-BUILDS.md)

## Inspect the evidence

[Released workflow results](docs/WORKFLOW-RESULTS.md) explain the comparison,
quality and same-tuning controls. The [Results page](https://developerjillur.github.io/ffmpeg-v2/benchmarks/)
also separates experimental optimization measurements from released-profile claims.
The [technical archive](https://developerjillur.github.io/ffmpeg-v2/reports/) retains
the complete development reports, rejected experiments and known gaps.

Public source version **0.6.1** provides portable setup and the existing workflow
policy. The quoted native timings are historical measurements, not a fresh public
packaging benchmark. The PGO candidate remains experimental and unpromoted. This
is a source-only release; native binaries, private media/profiles and runtime
databases are outside the distribution. Redacted evidence indexes are documentation,
not activation manifests. Some runtime diagnostics and historical reports are Bengali.

## Contribute and reuse

[Contributing](CONTRIBUTING.md) · [Roadmap](docs/ROADMAP.md) · [Security](SECURITY.md) ·
[Changelog](CHANGELOG.md) · [Publication policy](docs/PUBLICATION.md) · [Citation](CITATION.cff)

Toolkit license: [GPL-3.0-or-later](LICENSE). Preserve the applicable source and
license notices when reusing it. [Third-party notices](THIRD-PARTY-NOTICES.md) and
[upstream pin](upstream.lock.json) cover optional native source and dependencies.
