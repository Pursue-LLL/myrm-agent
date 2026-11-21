# core/security/path/

## Overview
Path security domain: the single import surface for every path protection rule in the
harness. Seven modules with one responsibility each, so a caller that only needs to
resolve a path safely never pulls protection policy into scope, and a caller that needs
policy never re-implements path parsing.

## File Index

| File | Role | Description | I/O/P |
|---|---|---|---|
| `__init__.py` | Package | Aggregation facade. Re-exports the public API and declares `__all__` so the `agent.security.path_security` shim forwards exactly this set and never widens it. | — |
| `pattern.py` | Core | Path-glob matcher SSOT — `compile_path_pattern` (segment-scoped `*`/`?`, recursive `**`, character classes, cached, consecutive `**/` collapsed), `path_matches_pattern` (relative patterns apply at any depth, absolute patterns anchored, dotfiles reachable; **case ignored by default** so a protected file cannot be reached by respelling it on APFS/NTFS), `first_matching_pattern` (names the rule that fired), `PathPatternMatch` (protected file + covering rule), `iter_matching_files` (bounded sweep: prunes dependency/build dirs, caps inspected files, logs when the cap trips), `normalise_path_pattern`. Its prune list is independent of the search-candidate pruner in `agent/meta_tools/file_search/fallback_discovery.py`. | ✅ |
| `filesystem.py` | Core | Generic path safety, no product policy — dangerous system roots (`DANGEROUS_PATHS`, built at import time from Unix roots, user-sensitive dirs and Windows roots), Windows reserved device names (`BLOCKED_DEVICE_NAMES`: `CON`, `PRN`, `AUX`, `NUL`, `CONIN$`, `CONOUT$`, `COM1`-`COM9` and `LPT1`-`LPT9` with their superscript-digit forms; matched with or without an extension, with the spaces before it dropped and with a `:` suffix cut off (`CON:` and `NUL:stream` are refused like `CON` and `NUL`; a drive letter is no device name), enforced on Windows only: `docs/aux.md` is an ordinary file elsewhere), absolute `/dev` `/proc` `/sys` prefixes and Windows device namespaces (a workspace-relative `dev/notes.txt` is an ordinary file), `is_network_or_nt_path` (a network share or NT-namespace spelling, decided on the text alone with no filesystem call, because opening such a path on Windows connects to the host it names and sends the user's credentials: the backslash forms `\\host\share`, `\\?\`, `\\.\` and `\??\` on every host, two or more leading slashes of either kind (`//host/share`, `///host`, mixed separators) only on a Windows host, since on POSIX `//tmp` is an ordinary absolute path) with `network_path_refusal` (the one refusal text every gate gives it), `expand_home` (a bare leading `~` or `~/...` expanded to the user's home, every other spelling unchanged: `os.path.expanduser` also reads `~name` as another user's home and, on Windows, turns the Office lock file `~$report.docx` into `C:\Users\$report.docx`, ordinary workspace names the file tools open as typed), `is_dangerous_path` (path inside a dangerous root), `covers_dangerous_path` (path equals or contains one — the counterpart that refuses a home directory, drive root or `/` as a write grant); both compare case-folded paths on macOS and Windows, whose default volumes ignore case (`FOLDS_CASE` is that flag, which the permission engine's refusing and asking rules read too), `is_blocked_device_path` (pre-IO static inspection of device names, device and network namespaces, then `lstat` mode checks; a network spelling is refused before the first filesystem call), `is_within_boundary` (symlink-escape immune), `safe_join_path` (null-byte, absolute-path, traversal and symlink defence; returns the *virtual* absolute path so bind mounts keep their prefix), `MAX_PATH_LENGTH`, `is_content_not_path` and `coerce_filesystem_path` runtime type guards. | ✅ |
| `bounded_read.py` | Core | `read_text_bounded(path, max_chars, boundary=None, errors="strict")` — the text read of a file whose content the product does not control (a repository's rule files, SKILL.md, MCP and repo config). It never reads past `max_chars + 1` characters (a longer file is `TOO_LARGE`, charged one character past the limit), refuses a path that resolves outside an optional `boundary` before opening it (`OUTSIDE_BOUNDARY`), and decides the kind of the file on the descriptor it then reads: the open is non-blocking and `fstat` must say regular file, so a FIFO, a device (a symlink to `/dev/zero`) or a directory is refused as `NOT_A_REGULAR_FILE` without a wait or a read. The text equals `Path.read_text` for the same file and `errors` (universal newlines, UTF-8). Missing files and permission errors are not caught and surface as `OSError`. Returns `BoundedRead(text, refusal, chars_read)` so a caller with a budget charges what the read cost; `ReadRefusal` names the three refusals. | ✅ |
| `confined_write.py` | Core | `open_directory_beneath(root, parts, create=True)` — the write counterpart of `bounded_read` for files the product creates in a folder that somebody else can also write (a workspace the sandboxed agent writes to). `root` is trusted (absolute, resolved by the caller, followed); every name of `parts` is opened with `O_NOFOLLOW` relative to the directory above it, so a symlink anywhere below the root, dangling or not, is refused as `UnsafeDirectoryError` and a file in the way as `NotADirectoryError`; missing directories are created the same way. The returned `ConfinedDirectory` holds the directory as a descriptor: `create_new(name)` creates a file exclusively below it (`O_CREAT\|O_EXCL\|O_NOFOLLOW`, so a symlink or hard link planted under the wanted name fails with `FileExistsError` instead of being opened) and returns the descriptor the caller writes through, `scandir()` lists that very directory, `unlink(name)` removes an entry, and a directory renamed or replaced after it was opened changes nothing. A closed directory refuses every use with `ValueError` instead of falling back to its path, which a link may have taken over. Names must be single path segments. Where descriptors cannot anchor a directory (Windows) each name is checked with `lstat` / `os.path.isjunction` before use: a link already in place is refused, the check-to-use window is not closed. | ✅ |
| `rules.py` | Core | Protected-path policy — `SENSITIVE_FILE_PATTERNS` (credentials, the local config encryption key, env files, cloud credentials, git config, databases, password files), `PROTECTED_INSTRUCTION_PATTERNS` (persona/guardrail instruction files, also matched through the symlink target; directory-scoped rules such as `.cursor/rules` cover the directory and everything under it, so emptying the directory is refused too), `EVIDENCE_READONLY_PATTERNS` (read-only session evidence and user inputs, covering both the directories themselves and their contents so `rm -rf evidence` is refused alongside `rm -rf evidence/report.pdf`), `EXECUTABLE_GIT_METADATA` (repo-relative `.git/config` and `.git/hooks` — the entries whose modification makes the host's next git call execute code, kept read-only by the OS sandbox) with `EXECUTABLE_GIT_METADATA_PATTERNS` (the same entries as match patterns, submodule git directories included, for the write gate that sees one path at a time), and the predicates that read them (`is_executable_git_metadata_file` backs the permission engine's write gate). | ✅ |
| `typed_path.py` | Core | The file a typed path opens, read once for every gate: `container_relative(path)` (the part of a path below the container alias `/workspace`, matched on whole segments: `/workspace2/x` is no alias; the one definition the executor, the observers and the saved-script reader share), `spelled_path(raw_path, workspace_root)` (with a workspace known the alias `/workspace/x` is `<workspace>/x`, a bare `~` is expanded by `expand_home`, a relative spelling is joined below the workspace) and `opened_path(raw_path, workspace_root)` (that place with every link followed; `None` for a text no file can be named by, a NUL byte or a lone surrogate, which a gate refuses instead of raising). The permission engine's path policy and rules, the session grant flow and the respelling probe all read a typed path through it, so they judge the file `CodeExecutor.resolve_path` opens and not another. | ✅ |
| `respelling.py` | Core | The on-disk name of a path typed with quotes, backticks, compatibility characters or decomposed accents: `generate_unicode_path_candidates` (the 7 normalization stages, deduplicated in stage order, every stage linear in the length of a text the model controls) and `find_existing_unicode_path(target_path, base_dir)`, the spelling `file_read_tool` opens when the typed one names nothing (`None` when the typed spelling exists). It probes the place the tools open (`typed_path.spelled_path`), judges a network or NT-namespace spelling on its text, the typed one and each candidate, before the first `exists` call (on Windows asking about such a path connects to the host it names), and never lands on a device or on a credential file by name that the typed text does not name: the credential labelling of a read keys to the typed text. Every other verdict (rules, forbidden directories, zones, the ask for a credential file or a link to one) is the permission engine's, which judges the typed and the respelled spelling alike (`agent/security/judged_paths.py`). | ✅ |

## Layering
```
pattern.py      no internal deps
filesystem.py   no internal deps
bounded_read.py → filesystem.is_within_boundary
confined_write.py  no internal deps
rules.py        → filesystem.is_content_not_path, pattern.first_matching_pattern
typed_path.py   → filesystem.expand_home
respelling.py   → filesystem.is_blocked_device_path, filesystem.is_network_or_nt_path, rules.is_sensitive_file, typed_path.spelled_path
__init__.py     → bounded_read, confined_write, filesystem, respelling, rules, typed_path
```
One direction only. `pattern` and `filesystem` know nothing about protection policy, so
the rule lists have exactly one home.

## Consumers
- `agent/meta_tools/file_ops/validators/` — `SensitiveFileValidator`, `EvidenceReadOnlyValidator`, `InvariantValidator`
- `agent/meta_tools/bash/_security/path_guard.py` — shell channel, via the predicates
- `agent/meta_tools/file_search/` — `grep_tool.py` and `rg_matches.py` withhold the lines of a sensitive file from a directory search, which no path check sees
- `find_existing_unicode_path`: `agent/meta_tools/file_ops/file_read_tool.py` opens the respelling of a path that names nothing, and `agent/security/judged_paths.py` has the permission engine judge that same respelling next to the typed one, so a read never opens a file no verdict has seen
- `agent/goals/invariant_snapshot.py` — post-hoc tamper detection
- `agent/workspace_rules/rule_read_guard.py`, `backends/skills/local.py` (workspace scan), `agent/security/workspace_trust/manifest.py` and `repo_policy.py` — `read_text_bounded` for files read before the folder is trusted
- `agent/security/path_security.py` — stable `agent.security.*` shim over this package
- the gates a tool call's path passes through, each refusing a network share or NT-namespace spelling before anything opens it (`is_network_or_nt_path`, `network_path_refusal`): the permission engine's `agent/security/checks.py` (`check_path_policy`, a DENY) and the grant flow in `agent/security/session_access.py`, `file_read_tool.py`, `file_ops/validators/path_validator.py`, and `CodeExecutor.resolve_path` in `toolkits/code_execution/executors/base.py`
- `expand_home`, so the file a tool opens is the home file the permission engine judged and not a directory named `~` below the working directory: `CodeExecutor.resolve_path` in `toolkits/code_execution/executors/base.py` and `file_ops/validators/path_validator.py`; `opened_path` reads a typed path the same way (the alias `/workspace` is the workspace; nothing else is expanded: `$HOME` and `~name` are names, as the tools open them) for `check_path_policy` in `agent/security/checks.py`, the grant directory in `agent/security/session_access.py` and, through `spelled_path`, the respelling probe
- `container_relative`, the alias reading itself: `CodeExecutor.resolve_path` in `toolkits/code_execution/executors/base.py`, `WorkspacePathResolver.to_local_path` / `is_container_path`, `toolkits/code_execution/saved_script.py`, and the observers `file_ops/observers/format_observer.py` and `artifact_observer.py`
- `core/security/types.py` (`PathPolicy`), `core/security/privacy/ladder.py`, `core/security/guards/privacy_ladder.py`
- `toolkits/browser/session/download/storage.py` — `open_directory_beneath` for every file a browser download keeps in the workspace
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
