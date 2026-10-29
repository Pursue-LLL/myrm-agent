# executors/

## Overview
Executors module for Agent-in-Sandbox mode.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Executors module for Agent-in-Sandbox mode. | — |
| base.py | Core | Code executor base classes, including default file I/O (`resolve_path` confines to the workspace plus granted directories), atomic replace file-write contract and `file_size` (regular-file size without reading content; refuses directories, FIFOs, devices and sockets). | ✅ |
| granted_roots.py | Core | `granted_root_containing` / `refuse_write_into_readonly_grant`: the executor's boundary is the workspace plus the directories granted for this run (declared, remembered for the session, or opened once by an approved call; `reachable_access_roots()`), the most specific root deciding and a writable one winning a tie, each root compared as stored against the target's real path (a link swapped into a root's place does not widen it); a write into a directory granted read-only is refused (workspace paths never are), by `LocalFileOpsMixin._guard_write` (every mutation, `mkdir` included) and by the base class's shell-based writes. | ✅ |
| gunzip.py | Core | `gunzip_bounded`: transparent `.gz` text reads decompress at most `MAX_GUNZIP_BYTES`, so one read cannot exhaust memory whatever the compression ratio. | ✅ |
| middleware.py | Core | `CodeExecutorMiddleware`: decorator that forwards every executor operation to an inner executor; a new `CodeExecutor` operation must be forwarded here too. | ✅ |
| execution_evidence.py | Core | Per-scope record that a process was actually launched; the verifier's PASS gate reads it. | ✅ |
| models.py | Core | Data models for code execution (`ExecutionContext.cancel_token`: set only by agent-facing tool calls, so goal verification and housekeeping runs are not cut by a stop). | ✅ |
| shell_file_transfer.py | Core | Chunked byte-exact file read (hex via `dd` + `od`) and write (base64) for shell-only executors, immune to stdout truncation and scrubbing. | ✅ |
| test_executor.py | Core | Subprocess-based test execution for skill evolution TDE. | ✅ |

| Submodule | Description |
|-----------|-------------|
| common/ | Common executor components. |
| local/ | Local executor module with native pathlib I/O and atomic write overrides. |

## Key Dependencies

- `core`
