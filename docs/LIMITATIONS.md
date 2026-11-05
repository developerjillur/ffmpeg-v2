# Known limitations and release boundaries

- Execution supervision is macOS-specific; Apple Silicon/M4 Max is the measured
  environment. Linux, Windows and every Intel Mac are not certified targets.
- FFmpeg/FFprobe are external dependencies. A listed codec or hardware feature is
  not a successful encode or proof of GPU use on your machine.
- Native build, patch, engine activation, immutable release and trusted exec
  commands need the full source checkout and fresh local acceptance evidence.
  The redacted historical indexes cannot activate an engine.
- No prebuilt native engine, benchmark media, private PGO profile or runtime
  database is distributed here. Research scripts require their own retained
  corpus and receipts. Path configuration alone does not recreate that lab.
- Phase 11's complete HD workflow passed its bounded timing gate. Direct HD/raw
  sample requirements failed. The candidate is experimental, with no complete
  new-prefix FATE/soak/install promotion acceptance. Original local 0.6.0 remains
  the verified lab default; public 0.6.1 is a source/portability release.
- CPU instruction reductions, metadata byte differences and warmup timing are not
  compression or general speedup claims. Different experiment epochs are not pooled.
- HDR, interlaced, variable-frame-rate, subtitles, audio and container policies
  have explicit supported bounds. Unsupported combinations fail closed. A
  successful tone-map is not a perceptual HDR mastering certification.
- Output validation is bounded by the selected workload and local decoder. It
  does not establish universal perceptual quality for every camera or codec.
- Resource limits are sampled watchdogs. Abrupt power/storage loss and
  kernel/system-wide scheduling behavior remain outside the application's control.
- Some diagnostics and historical reports are Bengali. English setup/reference
  guides and stable error identifiers are available.

See [historical gap register](GAPS.md), [readiness](READINESS.md),
[benchmark method](BENCHMARKS.md) and [report archive](REPORTS.md).
