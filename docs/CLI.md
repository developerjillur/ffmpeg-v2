# CLI reference

Run `ffv2 --help` and `ffv2 COMMAND --help` for exact arguments. Global options
precede the command. Every spec is a bounded JSON object; arbitrary FFmpeg argv
and shell strings are not accepted as job fields.

| Command | Behavior |
|---|---|
| `doctor [--refresh]` | Inspect backend capabilities, live resource admission and engine selection. No encode. |
| `probe PATH` | Read bounded local media metadata. |
| `plan SPEC.json` | Validate a typed specification and show the concrete plan. No encode. |
| `submit SPEC.json [--key KEY]` | Queue a job with optional idempotency key. No automatic worker. |
| `run SPEC.json [--key KEY]` | Submit and execute one job under supervision. |
| `worker [--drain] [--job-id ID]` | Run one sequential worker pass; drain is bounded. |
| `jobs [--limit N]` | Inspect recent jobs. |
| `status ID [--events]` | Inspect status, progress and receipts. |
| `cancel ID` | Request cancellation of that job and its owned processes. |
| `retry ID` | Queue another attempt while retaining previous evidence. |
| `mcp` | Serve the eight-tool stdio JSON-RPC interface. |
| `benchmark-plan INPUT --output-dir DIR` | Plan a small, bounded local comparison. |
| `benchmark INPUT --output-dir DIR` | Run that comparison; results apply to its exact workload. |
| `upstream status / prepare / build / resume` | Inspect or build optional locked native source in isolation. |
| `engine status / activate / deactivate` | Explicit selection of a verified native engine. |
| `release status / install / activate / rollback` | Local immutable code/engine lifecycle with matching acceptance evidence. |
| `exec --work-dir DIR -- PROGRAM ...` | Trusted local consumer under native engine bindings and watchdog. |

The trusted `exec` CLI is not exposed through MCP. Native activation, releases and
exec require fresh, matching local artifacts; the redacted public historical
indexes cannot activate an engine. Use a source checkout for those commands.

Global options: --state-dir sets a private runtime location inside allowed roots;
--input-root can be repeated for MCP read access. See [configuration](CONFIGURATION.md)
for environment variables. The explicit --ignore-system-memory override bypasses
system pressure/headroom/swap checks for that invocation; it is not recommended as
a default, and disk, mount, own-footprint, timeout and output limits remain active.

## Job operations

| Operation | Purpose | Example |
|---|---|---|
| transcode | Software or explicitly selected hardware video conversion | [HD](../examples/transcode-software-hd.json) |
| audio | PCM audio extraction | [Audio](../examples/audio.json) |
| remux | Container remux, with documented trim limitations | [Remux](../examples/remux.json) |
| frame | One frame at a timestamp | [Frame](../examples/frame.json) |
| contact_sheet | Bounded visual sampling | [Contact sheet](../examples/contact-sheet.json) |
| concat | Compatible copy or explicit normalization | [Concat](../examples/concat-normalize.json) |
| subtitle | Local subtitle burn-in | [Subtitle](../examples/subtitle.json) |
| audio_mix | Typed audio mixing | [Mix](../examples/audio-mix.json) |
| image | Bounded image conversion | [Image](../examples/image.json) |

Example paths are placeholders; replace them with paths in your allowed workspace.
Inspect the exact schema in ffv2/planner.py. HDR, interlace, scaling and codec
capability checks can refuse unsupported combinations. Listing VideoToolbox support
does not prove a job used the GPU or preserved a mastering intent.
