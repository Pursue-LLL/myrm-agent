# tests/backends/

## Overview

Tests mirroring `src/myrm_agent_harness/backends/` — profiles, secrets, and skills storage adapters.

## Submodule Index

| Path | Coverage |
|------|----------|
| `skills/` | Skill backend protocols, factory, listing, scanning, decorators, `config_version` Volume persistence |
| `skills/scanning/` | Static/AST/LLM skill security scanners |
| `skills/decorators/` | Version-aware and quarantine-aware decorators |
| Root `test_*.py` | Cross-cutting backends (profiles, secrets) |

## Key test files

| File | Role |
|------|------|
| `skills/test_config_version.py` | `MYRM_DATA_DIR/.skill_config_version` bump/get, corrupt-file fallback + WARNING log |
| `skills/test_local_backend_edge_cases.py` | Local skill backend and workspace scan on untidy folders: one bad skill costs only itself, archived skills hidden, a snapshot file left by an older version ignored, edits visible in the next listing, workspace trust gate, resource lookups |
| `skills/test_content_memo.py` | `ContentMemo` contract: one derivation per exact text, scope and byte-level key sensitivity, failures and refused values not pinned, entry and size bounds, LRU order, thread safety |
| `skills/scanning/test_scan_memo.py` | Memoized `scan_skill_content`: equals a fresh scan, edits rescanned, copies independent, huge finding lists not pinned, directory scan reuses it |
| `skills/test_frontmatter_memo.py` | Memoized `parse_skill_frontmatter`: equals a fresh parse, returned objects independent, invalid frontmatter fails every time |
| `skills/test_listing_memo.py` | Skill listing derives nothing twice for unchanged files, sees every edit, cannot be altered through a returned skill, and keeps availability live |

## Key Dependencies

- Design reference: [backends/_ARCH.md](../../src/myrm_agent_harness/backends/_ARCH.md)
- Skills module: [skills/_ARCH.md](../../src/myrm_agent_harness/backends/skills/_ARCH.md)
