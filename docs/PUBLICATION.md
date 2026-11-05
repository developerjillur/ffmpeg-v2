# Public source publication

Maintainer: Jillur Rahman. Source release: 0.6.1. Date: 2026-11-05.

This is a clean public snapshot of the local workflow toolkit, based on local
source revision 3f69dc22a333a326e12c63266b4772095133f7b9. Private Git history,
runtime state, personal client configurations, credentials, media, native builds
and PGO profiles are excluded. The original local source and installed engines
remain separate. All original tracked development reports are retained.

## Changes for public reuse

- Per-deployment project, work, mount and lock configuration replaces fixed owner
  paths. Worker and supervisor processes preserve the selected workspace.
- The former lab's 400 GB boot-used ceiling is opt-in; free-space, own-footprint,
  memory, mount, timeout and output guard defaults remain in effect.
- Client-neutral MCP configuration printing replaces personal client-file editing.
- English guides, a static documentation site, community templates, source CI and
  website/browser checks support reuse.
- Optional native source patches, their checksums and upstream license notices
  are preserved byte-for-byte. No native candidate is promoted by publication.

## Evidence handling

Private filesystem roots, host name and storage UUID are replaced with explicit
placeholders. Historical JSON indexes have a publication field containing the
original private source-file SHA-256 and their documentation-only status. Redaction
changes public JSON bytes; the original local evidence is retained separately.

Phase 11's paired analyses retain exact accepted whole-block ratios, times and
the original source-report hashes, with their report path redacted. The smaller
summary includes the estimator, counts, controls, quality and promotion decision.
They are inspectable historical evidence, not a public independent replication
or a local release activation manifest. The raw media/profiles/full process
receipts needed for the full lab are not distributed.

The source unit suite and installed CLI/MCP checks validate the public code.
Website checks validate generated pages, links, benchmark presentation, accessibility
and browser interactions. Neither suite certifies a native/GPU speedup. Original
phase test counts refer to their original source revisions; current CI is linked
from the README.

Source-only releases contain a complete Git source archive and checksums. Large
local engine artifacts are intentionally absent. Rebuilding or distributing a
native engine requires its own dependency/license review and acceptance evidence.
