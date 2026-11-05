# Getting started with FFmpeg-v2

Use FFmpeg-v2 when a local application needs a reviewed media plan, a recoverable
queue and a verified result. FFmpeg supplies the codecs; this toolkit controls the
workflow. Start with the installed FFmpeg backend before considering a native build.

## Requirements

- macOS. Apple Silicon is the verified target; Intel/macOS behavior is not certified.
- Python 3.9 or newer, Git, FFmpeg and FFprobe on PATH.
- Default admission: 10 GiB physical headroom, 20 GiB boot free space, estimated
  output plus 15 GiB output-volume reserve. The job limit is 12 GiB sampled footprint.
- A local input and a new output inside your allowed project/work roots.

Read [configuration](CONFIGURATION.md) for exact guard semantics. A machine's
total installed RAM does not establish current headroom. A refusal is a reason to
wait or reduce demand. Use small inputs first.

## Install from the repository

```sh
git clone https://github.com/developerjillur/ffmpeg-v2.git
cd ffmpeg-v2
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/ffv2 --version
```

FFmpeg is installed separately. On an existing Homebrew installation,
`brew install ffmpeg` is one option; verify both `ffmpeg -version` and `ffprobe
-version`. This repository does not silently install or replace either binary.
The install command above installs local Python code and its build backend; the
toolkit has no Python runtime dependencies.

## Create a dedicated workspace

```sh
mkdir -p media-project
export FFV2_PROJECT_ROOT="$PWD/media-project"
export FFV2_WORK_ROOT="$FFV2_PROJECT_ROOT/.ffv2-work"
.venv/bin/ffv2 doctor
```

Put your input.mp4 inside media-project. For a mounted external drive, set
FFV2_WORK_ROOT to an existing workspace there. Check the drive is mounted before
creating files. Paths under /Volumes are checked before directory creation.

Create media-project/job.json:

```json
{
  "operation": "transcode",
  "input": "input.mp4",
  "output": "preview.mp4",
  "encoder": "software",
  "duration": 5,
  "threads": 2
}
```

Review the plan before running it:

```sh
(cd media-project && ../.venv/bin/ffv2 probe input.mp4)
(cd media-project && ../.venv/bin/ffv2 plan job.json)
(cd media-project && ../.venv/bin/ffv2 run job.json)
```

Relative spec paths resolve from the CLI working directory, not the JSON file's
directory. Choose a fresh output name for each job. Existing output files are
preserved. Inspect the returned job and its receipt; validation includes a full
decode, metadata and checksum before no-clobber publication.

## Separate submission from execution

```sh
(cd media-project && ../.venv/bin/ffv2 submit job.json --key preview-001)
.venv/bin/ffv2 jobs
.venv/bin/ffv2 worker --drain
.venv/bin/ffv2 status JOB_ID --events
```

Replace JOB_ID with the returned 32-character identifier. A worker is sequential;
drain is bounded to 100 jobs per pass. Status may show waiting_resources,
interrupted, failed or cancelled rather than completed. Review the structured
reason and retained partials before retrying.

## Next steps

[CLI reference](CLI.md) · [MCP setup](MCP-PUBLIC.md) · [Python integration](PYTHON.md) ·
[Examples](../examples/) · [Configuration](CONFIGURATION.md) ·
[Native source builds](NATIVE-BUILDS.md) · [Limitations](LIMITATIONS.md)
