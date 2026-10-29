# core/security/path/

## Overview
Path security domain: the single import surface for every path protection rule in the
harness. Four modules with one responsibility each, so a caller that only needs to
resolve a path safely never pulls protection policy into scope, and a caller that needs
policy never re-implements path parsing.

## File Index

| File | Role | Description | I/O/P |
|---|---|---|---|
| `__init__.py` | Package | Aggregation facade. Re-exports the public API and declares `__all__` so the `agent.security.path_security` shim forwards exactly this set and never widens it. | — |
| `pattern.py` | Core | Path-glob matcher SSOT — `compile_path_pattern` (segment-scoped `*`/`?`, recursive `**`, character classes, cached, consecutive `**/` collapsed), `path_matches_pattern` (relative patterns apply at any depth, absolute patterns anchored, dotfiles reachable; **case ignored by default** so a protected file cannot be reached by respelling it on APFS/NTFS), `first_matching_pattern` (names the rule that fired), `PathPatternMatch` (protected file + covering rule), `iter_matching_files` (bounded sweep: prunes dependency/build dirs, caps inspected files, logs when the cap trips), `normalise_path_pattern`. Its prune list is independent of the search-candidate pruner in `agent/meta_tools/file_search/fallback_discovery.py`. | ✅ |
| `filesystem.py` | Core | Generic path safety, no product policy — dangerous system roots (`DANGEROUS_PATHS`, built at import time from Unix roots, user-sensitive dirs and Windows roots), Windows reserved device names (`BLOCKED_DEVICE_NAMES`, enforced on Windows only: `docs/aux.md` is an ordinary file elsewhere), absolute `/dev` `/proc` `/sys` prefixes and Windows device namespaces (a workspace-relative `dev/notes.txt` is an ordinary file), `is_dangerous_path` (path inside a dangerous root), `covers_dangerous_path` (path equals or contains one — the counterpart that refuses a home directory, drive root or `/` as a write grant); both compare case-folded paths on macOS and Windows, whose default volumes ignore case, `is_blocked_device_path` (pre-IO static inspection plus `lstat` mode checks), `is_within_boundary` (symlink-escape immune), `safe_join_path` (null-byte, absolute-path, traversal and symlink defence; returns the *virtual* absolute path so bind mounts keep their prefix), `MAX_PATH_LENGTH`, `is_content_not_path` and `coerce_filesystem_path` runtime type guards. | ✅ |
| `bounded_read.py` | Core | `read_text_bounded(path, max_chars, boundary=None, errors="strict")` — the text read of a file whose content the product does not control (a repository's rule files, SKILL.md, MCP and repo config). It never reads past `max_chars + 1` characters (a longer file is `TOO_LARGE`, charged one character past the limit), refuses a path that resolves outside an optional `boundary` before opening it (`OUTSIDE_BOUNDARY`), and decides the kind of the file on the descriptor it then reads: the open is non-blocking and `fstat` must say regular file, so a FIFO, a device (a symlink to `/dev/zero`) or a directory is refused as `NOT_A_REGULAR_FILE` without a wait or a read. The text equals `Path.read_text` for the same file and `errors` (universal newlines, UTF-8). Missing files and permission errors are not caught and surface as `OSError`. Returns `BoundedRead(text, refusal, chars_read)` so a caller with a budget charges what the read cost; `ReadRefusal` names the three refusals. | ✅ |
| `rules.py` | Core | Protected-path policy — `SENSITIVE_FILE_PATTERNS` (credentials, the local config encryption key, env files, cloud credentials, git config, databases, password files), `PROTECTED_INSTRUCTION_PATTERNS` (persona/guardrail instruction files, also matched through the symlink target; directory-scoped rules such as `.cursor/rules` cover the directory and everything under it, so emptying the directory is refused too), `EVIDENCE_READONLY_PATTERNS` (read-only session evidence and user inputs, covering both the directories themselves and their contents so `rm -rf evidence` is refused alongside `rm -rf evidence/report.pdf`), `EXECUTABLE_GIT_METADATA` (repo-relative `.git/config` and `.git/hooks` — the entries whose modification makes the host's next git call execute code, kept read-only by the OS sandbox) with `EXECUTABLE_GIT_METADATA_PATTERNS` (the same entries as match patterns, submodule git directories included, for the write gate that sees one path at a time), and the predicates that read them (`is_executable_git_metadata_file` backs the permission engine's write gate). | ✅ |

## Layering
```
pattern.py      no internal deps
filesystem.py   no internal deps
bounded_read.py → filesystem.is_within_boundary
rules.py        → filesystem.is_content_not_path, pattern.first_matching_pattern
__init__.py     → bounded_read, filesystem, rules
```
One direction only. `pattern` and `filesystem` know nothing about protection policy, so
the rule lists have exactly one home.

## Consumers
- `agent/meta_tools/file_ops/validators/` — `SensitiveFileValidator`, `EvidenceReadOnlyValidator`, `InvariantValidator`
- `agent/meta_tools/bash/_security/path_guard.py` — shell channel, via the predicates
- `agent/goals/invariant_snapshot.py` — post-hoc tamper detection
- `agent/workspace_rules/rule_read_guard.py`, `backends/skills/local.py` (workspace scan), `agent/security/workspace_trust/manifest.py` and `repo_policy.py` — `read_text_bounded` for files read before the folder is trusted
- `agent/security/path_security.py` — stable `agent.security.*` shim over this package
- `core/security/types.py` (`PathPolicy`), `core/security/privacy/ladder.py`, `core/security/guards/privacy_ladder.py`
- `toolkits/` — `code_execution/`, `storage/`, `filesystem_suggest/`, `wiki/`, `acp/`

Both protection layers resolve patterns through `pattern.py`, so the pre-write guard and
the post-hoc integrity check return the same verdict for the same file. A rule that
matches nothing is logged by `invariant_snapshot.py` instead of being counted as coverage.

## Known limits of the shell-channel guard

`agent/meta_tools/bash/_security/path_guard.py` decides from the text of the command: it unwraps
`sh -c`, strips `echo`/`printf` literals and matches protected names and operands. It does not
resolve what the command will actually open. A probe of 16 spellings that read `~/.ssh/id_rsa`
(`$HOME`, `./` segments, globs in the directory and file name, split quoting, a variable-assembled
name, `cd` then glob, command substitution, `printf` hex, `tar`, an env-passed segment) was refused
in 12 cases. The 4 that were allowed never put the path in the text: a pre-existing symlink to
the key, a path built from string pieces inside an interpreter (`python -c`), a base64-decoded
command piped to `sh`, and a `find -exec` walk selected by name pattern.

So the guard stops plainly spelled access, which is the case a prompt-injected or careless
command produces; it is not a boundary against a command written to evade it. Containing an
untrusted command is the execution sandbox's job (`toolkits/code_execution/EXECUTION_SYSTEM.md`),
and in LOCAL mode the OS permissions of the process. A rule added here must not be described as
protecting a file from the shell channel without that qualifier.

Every guard in this package — `is_sensitive_file`, `is_protected_instruction_file`
and `is_evidence_readonly_file` — inherits the matcher's case-insensitive default. That
default is the security invariant, not a convenience: APFS and NTFS resolve `Key.Pem`
and `key.pem` to one file, so a case-sensitive rule would let a protected credential be
reached by changing only its spelling. A caller that genuinely needs case-distinguishing
rules passes `case_sensitive=True`.
