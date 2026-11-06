# file_search/

## Overview
File search tool module (Claude Code compatible). Provides file name search and content search
with path-grouped densified output (auto-deduplicates repeated paths) and intelligent line truncation.
Both tools run in two tiers that follow one file-selection policy: ripgrep (`rg_traversal.py` decides what it walks,
`_rg_runner.py` runs it, `rg_matches.py` collects what it finds) and a Python tier (`fallback_discovery.py`,
`fallback_search.py`). One glob semantics (`glob_match.py`) selects the files of `glob_tool` on both tiers;
`grep_tool` hands its `file_pattern` to ripgrep's own `--glob`. What a call can still observe between the tiers
is listed under Tier Differences.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | File search tool module exports | — |
| glob_tool.py | Core | File search tool. Searches for files using glob patterns (`*`, `**`, `{a,b}`, root-anchored `/pattern`). The ripgrep tier only enumerates files (`rg --files --null` run from the search root with the `rg_traversal.py` flags, so a name that holds a line break stays one entry) and the shared matcher selects them. When ripgrep ends with status 2 after printing names (an unreadable directory) its listing stands, an empty one included; any other failure (a rejected flag, a kill, a crash) hands the listing to the Python tier (`fallback_discovery`). | ✅ |
| grep_tool.py | Core | Content search tool. Regex and literal (--fixed-strings) modes, `context_lines`. Path-grouped densified output, line truncation, non-code capping, and on the Python tier a footer that states how many files were searched and when the file cap or the time limit cut the scan short. Searches hidden files, skips ignored files, never follows symbolic links. A search over a directory never returns the lines of a sensitive file (`core.security.path.is_sensitive_file`: environment files, private keys, credential files) on either tier; naming such a file as `path` is a deliberate read and goes through the approval layer. ripgrep runs first whenever `rg` is on the PATH (looked up on every call, so one installed later is used at once); when it ends with status 2 after printing output (an unreadable directory) its answer stands, no match included, and when it fails any other way (look-around and back-references are Python-only, a single line beyond 16 MiB, a kill, a crash) or cannot start, the Python tier takes over. | ✅ |
| glob_match.py | Core | Glob semantics shared by both tools and both tiers: patterns without `/` match at any depth, a leading `/` anchors at the search root, `**` crosses directories, `{a,b}` expands (bounded), hidden files match; `normalize_glob` gives ripgrep's `--glob` and the matcher the same spelling (surrounding whitespace and a leading `./` dropped). Translated by the standard library's `glob.translate` and compiled with the `regex` engine, so stacked wildcards stay linear on deep paths; verified against ripgrep's own `--glob` matching by a parity matrix in the tests. | ✅ |
| _rg_runner.py | Internal | ripgrep process lifecycle: streams stdout line by line (a line ends at a line feed, or at a NUL byte for the `--null` listing of `glob_tool.py`; it may be up to 16 MiB, since `--json` puts a whole matching line into one event; a longer one kills the child and raises `ValueError`), supports stopping early once enough results are collected (drains the pipe so the exit is observed instead of hanging until the timeout), bounded runtime, kills and reaps the child on timeout, cancellation or a failing reader, closes stdin. The result carries the exit code, the first 4096 characters of stderr (a search over a system directory can print far more), the number of lines handed over and whether the run `answered`: status 2 after output means ripgrep searched on past an entry it could not open, so its lines stand (the runner logs that failure once, as a WARNING); a failure before any output (a rejected pattern or flag) searched nothing, and a kill or a crash cannot vouch for a partial result. `require_answer()` raises for a run that did not answer, and that is what sends each tool to the Python tier. | ✅ |
| rg_traversal.py | Core | ripgrep flags shared by glob and grep so that the ripgrep tier follows the Python tier's file-selection policy: user configuration never applies, hidden files are walked, version-control internals are excluded, and in a folder without a `.git` ancestor dependency/build directories are pruned and neither the ignore files of parent directories nor the user's global ignore file are read (inside a git checkout git's own ignore rules decide). | ✅ |
| rg_matches.py | Core | Grep rows collected from ripgrep's `--json` stream: match and context rows and the match cap. A search over a directory drops the lines of sensitive files here, before they count toward the cap. The stream's summary event is not read: before ripgrep 15 it counts only the files that printed output. | ✅ |
| fallback_discovery.py | Core | Candidate discovery policy and Python-tier discovery for glob/grep: version-control directories are never listed (`VCS_EXCLUDE_GLOB` is applied by the ripgrep tier too), ignore files apply unless the caller opts out, hidden files are listed, symbolic links are skipped, bounded scan. Inside a git checkout the listing is git's own, in git's order (each path once, though git names a path of a conflicted merge once per index stage; the order decides which files a file cap keeps), and a repository or submodule nested in it is listed by git in turn (two git processes each), and walked under the ignore files at its root only when git cannot read it (a configuration hardened git refuses, no checkout); a search root that git itself ignores (`node_modules/x`, `dist`) is walked like a plain folder. Outside git: the ignore files at the root plus the default prune list. Its prune list is independent of `core.security.path.pattern.PRUNED_DIR_NAMES`: a skip here costs search recall, a skip there would leave protected files uncovered. | ✅ |
| fallback_search.py | Core | Python-tier content search for grep: scans the candidate files that `fallback_discovery` selected with mmap, in concurrent batches, until the result cap or the time budget is reached, and returns the rows with the files of the batches it finished and whether the time budget ended the scan (`SearchOutcome`). A line is numbered and matched the way ripgrep does (only a line feed ends a line and the line ending is not part of the text a pattern sees; lines that are not UTF-8 are skipped), and each match carries its `context_lines` rows. | ✅ |
| path_hint.py | Core | Similar-path suggestions via Bounded Levenshtein-2, 7-stage Unicode normalization candidate generation, and existing path probing; `mcp_namespace_error` gives glob/grep a guided error for the virtual `/mcp` skill-doc namespace (read it with `file_read_tool`) | ✅ |
| skill_path_filter.py | Core | Block paths under disabled skill roots (from RunnableConfig `disabled_skill_roots`) | ✅ |
| _redaction.py | Internal | Per-file redaction of grep matches before formatting: each match line is redacted by the type of its file (`core.security.redact.redact_file_text`), so a source line such as `cancel_token: CancellationToken | None = None` reads the same as in `file_read_tool` while `.env`, YAML and JSON lines are redacted in full. Consecutive lines of one file are redacted together so a multi-line secret (a PEM block) is still masked. | ✅ |
| _formatter.py | Internal | Grep result formatter. Path-grouped densification (repeated path strings dropped once a result has 5 or more matches), line truncation, non-code capping, and the footers (how many files were searched, when known; the Python tier's file cap and time limit, and how to narrow the search). | ✅ |
| regex_validator.py | Core | Regex safety validator (ReDoS protection) | ✅ |

## Key Dependencies

- `agent.meta_tools._context_recovery` (`ensure_executor`: the executor that resolves the search path, recovered from the session stash when the ContextVar is lost)
- `utils` (ToolError, is_chinese)
- `core.security.safe_git` (hardened git invocation for the Python tier's git-aware listing)
- `core.security.path` (`is_sensitive_file`: the sensitive file patterns that a directory search withholds)
- `regex` (glob matching without catastrophic backtracking), `pathspec` (the ignore files at the root of a plain folder, or of a nested repository that git cannot read)

## Tier Differences

The tiers follow one file-selection policy, read a line the same way (a line is matched without its line ending;
`context_lines` rows surround each match) and withhold sensitive files from a directory search alike. What a call can
still observe:

- **Paths, order, whitespace**: ripgrep prints absolute paths, the Python tier paths relative to the searched
  directory (a one-file search: the file's own name). The order of results differs. A result line keeps its trailing
  whitespace under ripgrep only.
- **`file_pattern` against ignore rules**: ripgrep's `--glob` overrides ignore rules for whatever it matches, so it
  searches a git-ignored file that the pattern names or matches by wildcard (`*.log`), and an ignored directory beneath
  a directory-wide match (`packages/**`). The Python tier always honours the ignore files. Scope a search with `path`,
  not with a directory-level `file_pattern`.
- **`file_pattern` syntax**: `!` (negation), `#` (comment) and `\` (escape) are special to ripgrep only.
- **A file named as `path`**: ripgrep searches it whatever `file_pattern` says; the Python tier applies the pattern.
- **Binary and encoded files**: ripgrep gives up on a file at its first NUL byte (the whole file when the byte comes
  early) and decodes UTF-16 files that start with a BOM; the Python tier reads a file with NUL bytes whole and does
  not decode UTF-16.
- **Nested ignore files**: in a folder without `.git` (and in a nested repository that git cannot read), ripgrep
  honours the ignore files of every subdirectory, the Python tier those at the root only, so it can list a file that
  ripgrep would skip.
- **A search root that git ignores**: the Python tier walks it like a plain folder. ripgrep does too, unless an ignore
  file above the root covers it (a virtual environment's own `.gitignore` of `*`): then it finds nothing.
- **Files-searched count and scan limits**: only the Python tier states how many files it searched, and only the
  Python tier has a file cap (`max_search_files`); a note says when the cap, or the time limit
  (`search_timeout_seconds`), cut its scan short.
