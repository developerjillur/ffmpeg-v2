# Publication and documentation research

Date: 2026-11-05. Maintainer: Jillur Rahman.

## Product, audience and goal

The source implements a macOS local-media workflow controller, a typed JSON CLI,
an eight-tool stdio MCP server, a SQLite queue, independent supervision and strict
output validation. Optional FFmpeg C and x264 dependency patches are included.
It is an independent project, not an official FFmpeg release or a universal faster
encoder. The public release must preserve that distinction.

Primary readers: Apple Silicon developers integrating local media processing into
applications and MCP clients; maintainers who need inspectable queue behavior;
engineers comparing reproducible encoding experiments. The conversion goal is a
successful source checkout, reviewed plan and small local job, followed by a useful
issue or contribution. Stars are voluntary, not an acceptance metric.

Inputs reviewed: all tracked source files; CLI/MCP schemas; resource policy;
upstream and patch manifests; Phase 2–11 design/results; Phase 11 direct and complete
workflow analyses; the original clean local release and retained rollback records.
The complete local corpus, profiles and receipts are not in this small public
source repository. Redacted indexes are historical summaries, never activation
manifests. Public packaging changes are evaluated separately from old benchmarks.

## First-party references

| Source | Observation | Design implication |
|---|---|---|
| [FFmpeg documentation](https://ffmpeg.org/documentation.html) | FFmpeg supplies the underlying media engine and its own CLI. | Explain the workflow layer and optional patch set; link upstream and retain licenses. |
| [ffmpeg-python](https://github.com/kkroening/ffmpeg-python) | Python bindings focus on FFmpeg command/filter graphs. | Describe this project's typed jobs, supervision and receipts without claiming to replace other bindings. |
| [PyAV](https://pyav.org/docs/stable/) | Python access to media containers, streams and frames. | Make the subprocess/workflow boundary explicit; do not imply in-process frame APIs. |
| [HandBrake CLI](https://handbrake.fr/docs/en/latest/cli/cli-options.html) | A separate established transcoding CLI. | Present the local application/MCP integration use case, not unsupported superiority. |
| [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) | Static artifacts deploy using a Pages environment and scoped workflow permissions. | Build static HTML, validate it, then publish the same artifact. |
| [GitHub repository topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics) | Topics classify repositories for discovery. | Use a small relevant set of media, Python, macOS and MCP topics. |
| [Google sitemaps](https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview) | Sitemaps expose useful canonical URLs; indexing is not guaranteed. | Generate a sitemap and readable internal navigation; do not claim search ranking. |
| [Google title links](https://developers.google.com/search/docs/appearance/title-link) | Descriptive page titles help communicate page content. | Give each guide and report a unique title and summary. |
| [Structured data policy](https://developers.google.com/search/docs/appearance/structured-data/sd-policies) | Metadata must reflect visible content. | Use factual SoftwareSourceCode data; no invented ratings, downloads or offers. |

These are positioning references, not a comparative benchmark of other projects.
The pinned engine revision is retained as historical provenance, not asserted to
be the newest upstream version. No external provider, account or paid model is
required to build the static site.

## Evidence and limits

The Phase 11 complete HD workflow used nine accepted blocks at each of two added
CPU-load states. Paired elapsed time decreased 1.743% and 1.791% against Stock in
that workload. Direct HD accepted only 1/9 blocks in each state; raw accepted 3/9
and 7/9. Overall promotion failed. Those outcomes must appear together, including
failed and rejected experiments. CPU instruction reduction is not elapsed-time
proof. Container metadata differences are not compression improvements.

Unknowns: broad hardware/platform compatibility, a clean-room rebuild of the large
lab corpus, representative workloads beyond the published scope, overnight PGO
reliability, search indexing/ranking and community adoption. Do not fill them with
marketing claims. Public CI tests control behavior and source portability, not
native speed or GPU performance on every machine.

## Visual and accessibility direction

Use a compact documentation identity: warm paper, near-black ink, restrained green
and lime; a small terminal/receipt diagram; clear tabular benchmark evidence.
Avoid heavy media, client assets, external fonts, scroll interception and decorative
motion. Mobile navigation wraps naturally. Semantic headings, table captions,
visible focus, skip navigation, high-contrast text and reduced-motion support are
required. A scope switch should clarify workflow versus direct timing; all results
remain available in HTML without JavaScript. Copy buttons report success/failure.
No analytics, tracking or account signup is needed for reading documentation.

## Verification plan

Run both supported local Python test runtimes; install the source distribution in
an isolated environment; test CLI/MCP fresh-workspace behavior; scan the publication
allowlist for secrets and private paths. Build and crawl every generated local URL.
Run desktop/mobile/reduced-motion, keyboard, copy, table and browser-console checks
against the built artifact. Verify anonymous repository access, public release,
hosted workflow success and deployed HTTPS pages. Keep private publication audit
receipts outside the public checkout.

## Public positioning update — 2026-11-05

The maintainer requests a product-first presentation: lead with measured improvement,
the comparison with Stock FFmpeg, and why developers should use FFmpeg-v2. Internal
phase chronology belongs in the technical archive. Keep the existing visual identity
and static documentation stack; this is a content and information-hierarchy update.

The strongest released-profile comparisons are in the retained verification index:
22.6053968169% less HD workflow time and 28.4783443513% less live-action workflow
time versus the **prior Stock workflow preset**. Both use nine measured pairs and
pass quality/size and confidence gates. They compare a 4/2/2/4 Stock workflow with
an 8/2/2/8 native M4 Max profile. They are not comparisons with an automatically
tuned current Stock default or proof of a generally faster native encoder.
Same-tuning Stock controls must remain visible in Results: HD median 9.53% slower,
live-action median 0.84% faster, both intervals including equality. The experimental
PGO results stay in a clearly labeled research preview, separate from released
profile benefits. Do not rerun benchmarks or rewrite frozen historical evidence.

First-party capability checks refreshed against [FFmpeg CLI documentation](https://ffmpeg.org/ffmpeg.html)
and [FFmpeg formats documentation](https://ffmpeg.org/ffmpeg-formats.html). Stock
already provides thread controls, progress output, overwrite refusal and hash
formats. The product comparison must credit these building blocks and describe
the queue, supervision, integrated verification receipts and MCP interface that
FFmpeg-v2 adds. No invented workflow-setup percentage or compression gain.

Public journey: measured benefit and immediate baseline → what the toolkit adds
→ practical media/application/MCP use cases → installation → exact Results and
technical methods. Update the README, website, metadata and release description
consistently. Preserve original release assets and their source-bound audit.
