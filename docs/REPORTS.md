# Experiment and report archive

All tracked historical reports are retained, including regressions, rejected candidates
and remaining gaps. Dates and baselines belong to their own measurement epochs.
They are not pooled into a universal speedup claim. Original reports are mostly Bengali;
the [English benchmark guide](BENCHMARKS.md) explains the latest outcome.

| Phase | Focus | Outcome and documents |
|---|---|---|
| Initial / 2 | Typed workflows, native progress, Metal correctness | [Phase 2 results](PHASE2-RESULTS.md), [design](PHASE2-DESIGN.md), [initial validation](VALIDATION.md) |
| 3 | Reused supervision/capability work | [Results](PHASE3-RESULTS.md), [design](PHASE3-DESIGN.md) |
| 4 | Larger corpus, policies, GPU paths | [Results](PHASE4-RESULTS.md), [research](PHASE4-RESEARCH.md) |
| 5–7 | Recovery, long jobs, consumer/lifecycle checks | [Acceptance](PHASE4-7-RESULTS.md), [design](PHASE5-7-DESIGN.md) |
| 8 | M4 Max scoped thread-pool tuning | [Results](PHASE8-RESULTS.md), [research](PHASE8-RESEARCH.md) |
| 9 | Same-tuning HD/raw gaps and failed lookahead candidate | [Results](PHASE9-RESULTS.md), [research](PHASE9-RESEARCH.md) |
| 10 | Progress synchronization and per-worker/load/cache profiling | [Results](PHASE10-RESULTS.md), [research](PHASE10-RESEARCH.md) |
| 11 | Conditioned cache/load replay and experimental PGO | [Results](PHASE11-RESULTS.md), [research](PHASE11-RESEARCH.md), [English comparisons](BENCHMARKS.md) |

## Machine-readable evidence

[Phase 11 summary](benchmarks/phase11-summary.json), [direct paired analysis](benchmarks/phase11-direct-analysis.json)
and [complete-workflow paired analysis](benchmarks/phase11-workflow-analysis.json) include
exact accepted block counts, times, estimates and intervals. The [verification index
directory](verification/) retains redacted summaries for every development epoch.

Public index JSON files are **redacted historical summaries**, not valid local release
or activation manifests. Their publication field records the original private file's
SHA-256. Rewriting private paths changes public JSON bytes; original local evidence
remains retained privately. Raw media, PGO profiles, runtime queues and large native
artifacts are not bundled. This source publication does not claim an independent
public replication of the full local lab.

## Readiness and source

[Known public limitations](LIMITATIONS.md) · [historical gaps](GAPS.md) ·
[readiness](READINESS.md) · [native source](NATIVE-BUILDS.md) ·
[x264 patch source](../third_party/x264/README.md) · [upstream pin](../upstream.lock.json).

The public website renders the report archive with a searchable list. Every report
also remains directly readable in GitHub, without requiring the website or JavaScript.
