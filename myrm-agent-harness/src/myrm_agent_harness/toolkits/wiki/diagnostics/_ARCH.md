# wiki/diagnostics/

## Overview

Deterministic wiki quality measurement — zero LLM, zero agent tools. Consumed by
server `/wiki/stats`.

## Files

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Package marker and re-exports for the diagnostics module. | ✅ |
| `structural_lint.py` | Core | SSOT for broken markdown links and broken `[[wikilink]]` targets, both read through `core.link_extraction` (code, URLs and same-page anchors are not links; `#heading` suffixes are ignored); wikilinks resolve (by the same `core.link_resolver.WikiLinkResolver` that stores graph edges: path, title / alias, bare file name; read-only federated public pages are accepted too; a target that names several pages equally well is reported as ambiguous with the pages it matches, under the same `broken_wikilink` issue type), frontmatter type gate counts, and raw-backed provenance gaps | ✅ |

## Boundaries

- **In scope**: read-only vault scans
- **Out of scope**: LLM drift/consistency (WikiLinter maintain path), user-facing health scores, agent tools
