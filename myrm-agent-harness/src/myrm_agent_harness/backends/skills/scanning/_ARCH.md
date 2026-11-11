# scanning/

## Overview
Skill content security scanning — regex patterns, Python AST analysis, package manifest audit, dependency extraction, offline known-compromised package advisories matching, OSV.dev vulnerability intelligence (batch advisory lookup, full-record severity, CVSS v3 scoring) with TTL caching, advisory acknowledgment governance, LLM semantic audit, and secure ZIP extraction. `scan_skill_content` memoizes per exact content (see `backends/skills/_content_memo.py`).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports scanning APIs for agent and backend consumers. | — |
| ast_analyzer.py | Core | AST-level Python security analysis (eval, subprocess, pickle, etc.). | ✅ |
| archive_security.py | Core | Canonical archive security contract (error code/message), executable signature detection, and structured logs/metrics. | ✅ |
| cvss.py | Core | CVSS v3.x base score computed from an OSV vector string (v4 and malformed vectors yield `None`). | ✅ |
| dependency_extractor.py | Core | Manifest and lockfile dependency extractor for package.json (npm), requirements.txt (PyPI), pyproject.toml (PyPI), uv.lock (PyPI), bun.lock (npm; JSONC, resolved registry versions only), and package-lock.json (npm). | ✅ |
| llm_auditor.py | Core | LLM-based semantic threat detection beyond regex/AST coverage. Parses the finding object via `parse_llm_json_object` (robust against fences, prose, bare control chars, trailing commas). | ✅ |
| osv_scanner.py | Core | Online OSV.dev vulnerability intelligence scanner: the batch endpoint (100 queries per request) yields advisory ids only, so each unique advisory's full record is fetched once for its severity (database label, else CVSS v3 base score, else MEDIUM; `MAL-*` is CRITICAL; an unpinned dependency's findings are capped at MEDIUM) and text. Requests run with bounded concurrency and retry transient failures; whatever still cannot be queried is logged as a warning and the scan fails open; only fully resolved dependencies are cached; `resolve_severity=False` skips the record requests for latency-bound callers. | ✅ |
| package_audit.py | Core | package.json supply-chain audit (install scripts, suspicious deps, in-memory lifecycle script gate, entry point artifact physical reachability & non-empty integrity verification). | ✅ |
| patterns/ | Core | 技能安全扫描模式子包：injection/exfiltration/filesystem/network/system 五组纯数据 + types；`__init__` 按原顺序汇总 `ALL_PATTERN_GROUPS`。详见 [patterns/_ARCH.md](patterns/_ARCH.md) | ✅ |
| rescan_engine.py | Core | Installed skill multi-layer rescan orchestrator with AdvisoryAckRegistry governance and auto-quarantine disposition. | ✅ |
| scanner.py | Core | Single-content scanner (regex patterns, invisible Unicode, Python AST), its result types, scan summary aggregation and report formatting. `scan_skill_content` is memoized per (skill name, extension, exact content): a hit returns a fresh `ScanResult` copy, and a result with more than 128 findings is never pinned. | ✅ |
| directory_scanner.py | Core | Multi-file skill directory scan with file-count, file-size and wall-clock limits; each file goes through the memoized `scan_skill_content`. | ✅ |
| security_advisories.py | Core | Offline known-compromised package advisories catalog for zero-latency, deterministic detection of notorious malware. | ✅ |
| vuln_cache.py | Core | Vulnerability scan result cache with 24-hour TTL and disk persistence. | ✅ |
| zip_extract.py | Core | Secure ZIP extraction (compression ratio / entry-count / total-size limits, symlink/path traversal defense, executable-binary rejection). | ✅ |
| scanning_write_backend.py | Core | Framework-level security wrapper that enforces mandatory scanning before skill writes. | ✅ |
| path_security.py | Core | Filesystem path security (symlinks, Windows directory junctions) and category bucket collision defense (GitHub Issue #75983). | ✅ |

## Key Dependencies

- `backends.skills.types` (SecurityScanSummary, SecurityFindingDetail)
- `backends.skills._content_memo` (per-content memo of `scan_skill_content`)
