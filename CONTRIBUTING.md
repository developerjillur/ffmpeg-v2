# Contributing

Thanks for helping make local media workflows easier to inspect and verify.
Maintainer: Jillur Rahman.

Start with [setup](docs/GETTING-STARTED.md) and [architecture](docs/ARCHITECTURE.md).
Use a dedicated workspace and preserve source assets, outputs and rollback data.
Do not change another application's settings or replace system FFmpeg.

## Development checks

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
.venv/bin/python -B -W error::ResourceWarning -m unittest discover -s tests -v
npm ci
npm run build
npm run check
```

The Python suite includes macOS process/resource APIs; run it on macOS. CI runs
the source suite there and website checks separately. Unit tests do not prove a
codec/GPU/performance result. Browser checks use Playwright and axe-core. Node 22+
is a documentation development requirement, not a CLI runtime dependency.

Keep changes focused. Add a test when it can detect a meaningful behavioral
regression. Preserve typed errors, no-clobber publication, process identity checks,
local input restrictions and resource safeguards. Do not add raw shell execution
to MCP. Document externally visible behavior and relevant limitations.

## Reporting a bug or performance issue

Use the issue templates. Include version, OS/hardware, backend build, sanitized
typed spec, expected/actual behavior and concise logs. Remove private paths,
tokens and client data. Use a distributable minimal fixture or describe how to
create one. Performance reports must name the baseline, exact argv, quality,
warmups, rejected samples, cache/load conditions and uncertainty; include slow and
failed trials. Do not cherry-pick a faster run after a measured trial fails.

Security issues belong in [private vulnerability reporting](SECURITY.md), not a
public issue. Please follow [community conduct](CODE_OF_CONDUCT.md).
