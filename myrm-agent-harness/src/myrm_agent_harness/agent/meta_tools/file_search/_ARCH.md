# file_search/

## Overview
File search tool module (Claude Code compatible). Provides file name search and content search
with path-grouped densified output (auto-deduplicates repeated paths) and intelligent line truncation.
Both tools run in two tiers that search the same files: ripgrep (`rg_traversal.py` decides what it walks,
`_rg_runner.py` runs it) and a Python tier (`fallback_discovery.py`, `fallback_search.py`). One glob semantics
(`glob_match.py`) serves both, so a pattern means the same thing with or without ripgrep.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | File search tool module exports | — |
| glob_tool.py | Core | File search tool. Searches for files using glob patterns (`*`, `**`, `{a,b}`, root-anchored `/pattern`). The ripgrep tier only enumerates files (`rg --files` run from the search root with the `rg_traversal.py` flags) and the shared matcher selects them; the Python tier uses `fallback_discovery`. | ✅ |
| grep_tool.py | Core | Content search tool. Regex and literal (--fixed-strings) modes. Path-grouped densified output, line truncation, non-code capping. Searches hidden files, skips ignored files, never follows symbolic links. ripgrep runs first; when it fails after printing matches (an unreadable directory) the matches are kept, and when it fails without any (look-around and back-references are Python-only) the Python tier takes over. `file_pattern` follows the same glob semantics on every tier. Remaining tier differences: a `file_pattern` that names an ignored file explicitly still searches it under ripgrep (its `--glob` overrides ignore rules) but not under the Python tier; result paths are absolute under ripgrep and relative to the search path under the Python tier. | ✅ |
| glob_match.py | Core | Glob semantics shared by both tools and both tiers: patterns without `/` match at any depth, a leading `/` anchors at the search root, `**` crosses directories, `{a,b}` expands (bounded), hidden files match; `normalize_glob` gives ripgrep's `--glob` and the matcher the same spelling (surrounding whitespace and a leading `./` dropped). Translated by the standard library's `glob.translate` and compiled with the `regex` engine, so stacked wildcards stay linear on deep paths; verified against ripgrep's own `--glob` matching by a parity matrix in the tests. | ✅ |
| _rg_runner.py | Internal | ripgrep process lifecycle: streams stdout line by line, supports stopping early once enough results are collected (drains the pipe so the exit is observed instead of hanging until the timeout), bounded runtime, kills and reaps the child on timeout or cancellation, closes stdin. | ✅ |
| rg_traversal.py | Core | ripgrep flags shared by glob and grep so that the ripgrep tier walks the files the Python tier would: user configuration never applies, hidden files are walked, version-control internals are excluded, and in a folder without a `.git` ancestor dependency/build directories are pruned and ignore files of parent directories are not read (inside a git checkout git's own ignore rules decide). | ✅ |
| fallback_discovery.py | Core | Candidate discovery policy and Python-tier discovery for glob/grep: version-control directories are never listed (`VCS_EXCLUDE_GLOB` is applied by the ripgrep tier too), ignore files apply unless the caller opts out (git-aware listing, root ignore files in non-git directories), hidden files are listed, symbolic links are skipped, bounded scan. Its prune list is independent of `core.security.path.pattern.PRUNED_DIR_NAMES`: a skip here costs search recall, a skip there would leave protected files uncovered. | ✅ |
| fallback_search.py | Core | Python-tier content search for grep: scans the candidate files that `fallback_discovery` selected with mmap, in concurrent batches, until the result cap or the time budget is reached. | ✅ |
| path_hint.py | Core | Similar-path suggestions via Bounded Levenshtein-2, 7-stage Unicode normalization candidate generation, and existing path probing; `mcp_namespace_error` gives glob/grep a guided error for the virtual `/mcp` skill-doc namespace (read it with `file_read_tool`) | ✅ |
| skill_path_filter.py | Core | Block paths under disabled skill roots (from RunnableConfig `disabled_skill_roots`) | ✅ |
| _redaction.py | Internal | Per-file redaction of grep matches before formatting: each match line is redacted by the type of its file (`core.security.redact.redact_file_text`), so a source line such as `cancel_token: CancellationToken | None = None` reads the same as in `file_read_tool` while `.env`, YAML and JSON lines are redacted in full. Consecutive lines of one file are redacted together so a multi-line secret (a PEM block) is still masked. | ✅ |
| _formatter.py | Internal | Grep result formatter. Path-grouped densification (repeated path strings dropped once a result has 5 or more matches), line truncation, non-code capping | ✅ |
| regex_validator.py | Core | Regex safety validator (ReDoS protection) | ✅ |

## Key Dependencies

- `toolkits.code_execution` (executor for path resolution)
- `utils` (LRUCache, ToolError)
- `core.security.safe_git` (hardened git invocation for the Python tier's git-aware listing)
- `regex` (glob matching without catastrophic backtracking), `pathspec` (root `.gitignore` rules in non-git directories)
