# file_search/

## Overview
File search tool module (Claude Code compatible). Provides file name search and content search
with path-grouped densified output (auto-deduplicates repeated paths) and intelligent line truncation.
Both tools select files with one glob semantics (`glob_match.py`) on every search tier and run ripgrep
through one process runner (`_rg_runner.py`), so a pattern means the same thing with or without ripgrep.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | File search tool module exports | — |
| glob_tool.py | Core | File search tool. Searches for files using glob patterns (`*`, `**`, `{a,b}`, root-anchored `/pattern`). The ripgrep tier only enumerates files (`rg --files`, run from the search root) and the shared matcher selects them; the Python tier uses `fallback_discovery`. | ✅ |
| grep_tool.py | Core | Content search tool. Regex and literal (--fixed-strings) modes. Path-grouped densified output, line truncation, non-code capping. Three-tier search engine (ripgrep > mmap > Python); `file_pattern` follows the same glob semantics on every tier | ✅ |
| glob_match.py | Core | Glob semantics shared by both tools and both tiers: patterns without `/` match at any depth, a leading `/` anchors at the search root, `**` crosses directories, `{a,b}` expands (bounded), hidden files match. Built on the standard library's `glob.translate`; verified against ripgrep's own `--glob` matching by a parity matrix in the tests. | ✅ |
| _rg_runner.py | Internal | ripgrep process lifecycle: streams stdout line by line, supports stopping early once enough results are collected (drains the pipe so the exit is observed instead of hanging until the timeout), bounded runtime, kills and reaps the child on timeout or cancellation, closes stdin. | ✅ |
| fallback_discovery.py | Core | Candidate discovery policy and Python-tier discovery for glob/grep: version-control directories are never listed (`VCS_EXCLUDE_GLOB` is applied by the ripgrep tier too), ignore files apply unless the caller opts out (git-aware listing, root ignore files in non-git directories), hidden policy, bounded scan. Its prune list is independent of `core.security.path.pattern.PRUNED_DIR_NAMES`: a skip here costs search recall, a skip there would leave protected files uncovered. | ✅ |
| path_hint.py | Core | Similar-path suggestions via Bounded Levenshtein-2, 7-stage Unicode normalization candidate generation, and existing path probing; `mcp_namespace_error` gives glob/grep a guided error for the virtual `/mcp` skill-doc namespace (read it with `file_read_tool`) | ✅ |
| skill_path_filter.py | Core | Block paths under disabled skill roots (from RunnableConfig `disabled_skill_roots`) | ✅ |
| _redaction.py | Internal | Per-file redaction of grep matches before formatting: each match line is redacted by the type of its file (`core.security.redact.redact_file_text`), so a source line such as `cancel_token: CancellationToken | None = None` reads the same as in `file_read_tool` while `.env`, YAML and JSON lines are redacted in full. Consecutive lines of one file are redacted together so a multi-line secret (a PEM block) is still masked. | ✅ |
| _formatter.py | Internal | Grep result formatter. Path-grouped densification (repeated path strings dropped once a result has 5 or more matches), line truncation, non-code capping | ✅ |
| regex_validator.py | Core | Regex safety validator (ReDoS protection) | ✅ |

## Key Dependencies

- `toolkits.code_execution` (executor for path resolution)
- `utils` (LRUCache, ToolError)
- `core.security.safe_git` (hardened git invocation for the Python tier's git-aware listing)
