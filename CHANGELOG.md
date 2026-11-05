# Changelog

## 0.6.1 — 2026-11-05

First public source release of the existing local workflow toolkit.

- Configure project, scratch workspace, host lock and mount requirements per
  deployment; ordinary local workspaces no longer require the original lab drives.
- Make the original owner's boot-used ceiling an explicit optional setting while
  retaining free-space, memory, own-footprint, mount, timeout and output safeguards.
- Add English setup, CLI, MCP, Python and limitations guides, a static documentation
  site, community templates, source CI and publication checks.
- Include all historical Phase 2–11 reports, redacted summary indexes and Phase 11
  paired-block analyses, including failed/insufficient outcomes.
- Replace personal MCP configuration editing with a client-neutral configuration
  printer. No client file is automatically changed.

This version is a portable source/documentation release. It does not promote the
experimental Phase 11 PGO candidate or certify a new native engine. Benchmarks
remain measurements of their original code/engine/workload, not a fresh benchmark
of public 0.6.1 packaging. No native binary or private corpus is distributed.

## Earlier local phases

The 0.2–0.6 local development and experiment reports are retained in
[the report archive](docs/REPORTS.md). Their dates, baselines, outcomes and known
gaps are separate; local immutable release identifiers are not public GitHub tags.
