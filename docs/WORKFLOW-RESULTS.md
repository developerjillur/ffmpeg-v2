# Measured FFmpeg-v2 workflow improvements

The released M4 Max native profile reduced elapsed workflow time **22.61% for HD** and **28.48% for live action/VFX** against the prior Stock workflow preset. The workload includes planning, durable queueing, encode, metadata validation, complete strict decode, SHA-256 and staged no-clobber publication.

## Before and after

| 60-second source | Stock prior preset, s | V2 native profile, s | Less elapsed time | Trials / configuration | Full quality frames |
|---|---:|---:|---:|---:|---:|
| 1080p animation · 1920×1080 / 30fps | 9.7344 | 7.5339 | **22.61%** | 9 | 1,800 |
| Live action / VFX · 1920×800 / 24fps | 7.5278 | 5.3840 | **28.48%** | 9 | 1,440 |

**Baseline:** Homebrew Stock FFmpeg 9.0.2 with encoder/decoder/filter/validation pools **4/2/2/4**. Candidate: native n9.0.2-3-gb6e0de6-ffmpeg-v2-m4 with **8/2/2/8**. This changes tuning and uses an optional native source build; it is not a comparison against an automatically tuned or same-settings Stock default.

The earlier FFmpeg-v2 workflow is another reference: elapsed time decreased 22.31% on HD and 30.77% on live action. These reference labels must not be interchanged.

## Quality stayed within every declared gate

Same source/range, libx264 veryfast/CRF20 and AAC160k. Quality was not traded for a lower configured quality/bitrate target. All target frames were aligned and checked. Output size increased slightly; this is not a compression-ratio improvement.

| Source | VMAF before → after | ΔPSNR-Y dB | ΔSSIM | Output size change |
|---|---:|---:|---:|---:|
| 1080p animation | 94.761184 → 94.781527 | +0.004890 | +0.000001 | +0.162% |
| Live action / VFX | 93.375096 → 93.379144 | +0.000316 | +0.000002 | +0.024% |

Gates: ΔVMAF≥−0.10, ΔPSNR-Y≥−0.05dB, ΔSSIM≥−0.00001, size≤1.02×, faster median and upper paired confidence ratio<1 against the declared baseline. Native/Stock outputs at matching pools were byte-identical on these source ranges.

## Same-tuning Stock controls

Stock accepts the same thread controls. Applying the same 8/2/2/8 pools changes the question from packaged workflow improvement to engine comparison. That comparison does not establish a general native-encoder speed advantage.

| Source | V2 native, s | Matched Stock, s | V2 elapsed change | Ratio 95% interval |
|---|---:|---:|---:|---|
| 1080p animation | 7.5339 | 6.8781 | +9.53% | 0.979218–1.315438 |
| Live action / VFX | 5.3840 | 5.4297 | -0.84% | 0.625907–1.070255 |

Positive change means more elapsed time. Both matched-control intervals include equality. The HD median is 9.53% slower; live action is 0.84% faster, without a proven engine advantage. The product benefit is the coordinated workflow policy plus job control, verification and integration.

## Conditions and uncertainty

Apple M4 Max, 10P+4E, 36 GiB, macOS 27.2/arm64. Big Buck Bunny 1920×1080/30fps and Tears of Steel 1920×800/24fps, source range 60–120s. One excluded warmup then nine measured trials per configuration. Time reduction is one minus the ratio of total-time medians; 20,000 paired trial-block bootstrap draws supply uncertainty. Interpreter startup is excluded.

| Source | V2 / prior Stock ratio | Paired 95% interval |
|---|---:|---|
| 1080p animation | 0.773946 | 0.577062–0.879356 |
| Live action / VFX | 0.715217 | 0.670815–0.765480 |

The host was shared, work was sequential and nice≥10, with a task-scoped system-memory waiver; own-footprint, disk, mount, timeout and output guards remained. Busy-host scheduling and small sample scope limit extrapolation. Times are historical released-profile measurements, not a new public 0.6.1 packaging benchmark. No cross-platform or universal FFmpeg speedup is claimed.

The auto profile applies only to eligible >=60s M4 Max native-geometry, progressive square-pixel, unrotated 8-bit software quality transcodes with explicit matching fps≤30. Other workloads retain conservative policies. See [native builds](NATIVE-BUILDS.md) and [configuration](CONFIGURATION.md).

## Inspect the source evidence

[Machine-readable released workflow summary](benchmarks/released-workflow-summary.json) · [retained verification index](verification/phase8-2026-11-04.json) · [original detailed report](PHASE8-RESULTS.md).

Experimental PGO measurements are separate, remain unpromoted and are not added to these percentages. See the research preview in Results and the [technical archive](REPORTS.md) for failed and rejected outcomes.
