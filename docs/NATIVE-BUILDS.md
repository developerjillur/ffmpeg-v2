# Optional native source and patches

Normal typed workflows can use FFmpeg/FFprobe already on PATH. Build a native
candidate only if you need the patched progress/Metal behavior and can run the
complete local acceptance suite. No native binary is bundled with public 0.6.1.

The historical pinned FFmpeg base is n9.0.2, commit
946fcce07b6dcd0331c8cc609192aeff5e1924f8. This pin is provenance, not a statement
about the latest upstream release. Review [upstream.lock.json](../upstream.lock.json),
[patch checksums](../patches/manifest.json) and [licenses](../THIRD-PARTY-NOTICES.md).

| Patch | Purpose |
|---|---|
| 0001-jsonl-progress.patch | Optional versioned JSONL progress; existing key/value progress remains default. |
| 0002-metal-runtime.patch | Optional Metal runtime compilation when offline tools are unavailable. |
| 0003-metal-lifetime.patch | Fix lifetime/ownership cleanup of autoreleased Metal command objects. |

Review plans from a full source checkout:

```sh
ffv2 upstream status
ffv2 upstream prepare --plan
ffv2 upstream build --profile native --jobs 1 --plan
```

Preparing source and building are separate explicit actions; omit --plan only
after reviewing requirements, disk/memory budgets and the exact plan. Existing
source is not silently overwritten. The patch script checks the clean locked
base and each SHA-256 before applying. Historical baseline/m4 profiles depend on
Apple Silicon/Homebrew library paths; they are not universal build recipes.
See [detailed historical build method](UPSTREAM.md).

The x264 patches and PGO recipe under third_party/x264 are experimental. Their
codec-mode/quality results do not imply full release acceptance. A new build must
pass its own native, FATE, GPU, fault, soak, consumer and lifecycle checks before
activation. Never copy an old engine's receipts to accept another prefix.
