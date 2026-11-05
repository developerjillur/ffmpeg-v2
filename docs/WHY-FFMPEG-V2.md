# Why use FFmpeg-v2?

Use FFmpeg-v2 to make FFmpeg work repeatable inside an application: a tuned policy,
a typed job, a recoverable queue and a verified output. It combines the media
engine's existing capabilities with the execution control that local tools need.

## Measured improvement you can inspect

In the recorded M4 Max native-profile comparison, a 60-second HD workflow took
**22.61% less elapsed time**, and a 60-second live-action/VFX workflow took
**28.48% less**, versus the prior Stock workflow preset. Both passed the declared
quality, size and confidence gates across nine measured trials per configuration.

The comparison changes encoder/decoder/filter/validation pools from 4/2/2/4 to
8/2/2/8. It is a workflow-tuning result using an optional native engine, not an
out-of-the-box Stock default comparison. The [Results page](WORKFLOW-RESULTS.md)
shows before/after seconds, quality, uncertainty and same-tuning Stock controls.

## What it adds to Stock FFmpeg

| Need | Stock FFmpeg provides | FFmpeg-v2 adds |
|---|---|---|
| Tune local work | Codec and filter thread controls | A measured M4 Max policy coordinating encoder, decoder, filter and validation pools |
| Integrate with an app | CLI commands and media libraries | Typed JSON plans, stable error codes, source/backend identities and Python interfaces |
| Run a batch | Individual command execution | Durable SQLite queue, idempotency, priority, cancel/retry and retained attempt history |
| Track execution | Progress output | A job lifecycle, stored events, explicit worker control and a verification receipt |
| Verify a result | Decode and hash building blocks | Automatic metadata/full-decode/SHA-256 validation before staged publication |
| Preserve outputs | Overwrite-refusal options | No-clobber publication tied to a validated job and output reservation |
| Connect MCP | Your integration around CLI/library calls | Eight typed local-file tools using the same planner and queue |
| Watch resource demand | Command-level controls | Independent supervision with system pressure, owned footprint, disk, deadline and parent checks |

FFmpeg's existing [CLI controls](https://ffmpeg.org/ffmpeg.html) and
[hash formats](https://ffmpeg.org/ffmpeg-formats.html#framehash) are building blocks
for these workflows. The toolkit makes their composition reusable and inspectable.

## Three practical reasons to adopt it

**Spend less time rebuilding orchestration.** Submit a typed specification instead
of implementing a different queue/progress/retry/verification path in each tool.
Integration effort has not been given an invented percentage.

**Make a media job accountable.** An exact plan, fingerprints, events, retained
attempts and a final receipt explain what ran and what passed. Full-decode checking
and hashing remain part of the measured workflow rather than being removed for speed.

**Keep local work controlled.** The worker is sequential and an independent
supervisor stops only the owned job on timeout, cancellation or resource failure.
MCP works on explicitly allowed local files and does not expose arbitrary shell argv.

## Optional native enhancements

For the pinned FFmpeg source base, the optional native patch set adds versioned
JSONL progress, optional Metal runtime compilation when offline tools are missing,
and Metal command-object lifetime fixes. These are explicit source-build features;
the existing FFmpeg backend remains usable for ordinary typed jobs. See
[native setup and patch provenance](NATIVE-BUILDS.md).

## Where it fits

- Transcription/search pipelines: PCM audio, frames and contact sheets.
- Media application exports: transcode, remux, concat, subtitles, audio mixing and images.
- MCP tools and Python applications: explicit planning, queueing, worker start and polling.

The typed interface covers nine operations. Direct FFmpeg remains available for
free-form filtergraphs, streaming and other engine features outside that interface.
The verified execution target is macOS/Apple Silicon. See [setup](GETTING-STARTED.md),
[supported operations](CLI.md), [configuration](CONFIGURATION.md) and [limitations](LIMITATIONS.md).
