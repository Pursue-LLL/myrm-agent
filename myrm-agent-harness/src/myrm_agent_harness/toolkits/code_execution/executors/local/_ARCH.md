# local/

## Overview
Local code executor module. Executes Python code and Bash commands on the
host machine using subprocesses, persistent sessions, and OS-level sandboxing.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports `LocalExecutor`. | — |
| executor.py | Core | Orchestrator: Python execution, persistent-shell lifecycle, workspace binding and the composed services; its bash path is `LocalBashMixin`. A bash command may name the granted directories only while an OS sandbox enforces them (`_command_whitelist`). | ✅ |
| _bash_exec.py | Core | `LocalBashMixin`, the bash path of `LocalExecutor`: `execute_bash`/`execute_bash_stream` validate and audit the command the agent issued (`context.original_code`), run the prepared script in the persistent shell, and hand the context's `cancel_token` and the command's `CommandEnv` to it. The shell itself starts with a sanitized environment that holds no credentials. | ✅ |
| _bash_sessions.py | Helper | Which persistent shell serves a command: `shell_grants` (the granted directories the shell's sandbox may open: none without an enforcing OS sandbox), `get_or_create_bash_session` (the key carries a signature of the grants, so a changed set starts a new shell and closes the old one), `close_bash_sessions`, `grant_command_paths` (what the command validator is relaxed for). | ✅ |
| _command_env.py | Helper | What one bash command may read: `scrubbed_user_env` (skill/global settings minus host-secret names), `collect_command_credentials` (user OAuth credentials filtered by `allowed_credential_issuers`, plus single-use ephemeral credentials consumed against the command's digest), `build_command_env`. | ✅ |
| _file_ops.py | Core | Native file I/O (read/write/delete/list; `file_size` is a `stat` that refuses non-regular files; `.gz` reads are size-bounded) via pathlib. Every mutation passes `_guard_write`, which refuses the executor's configured read-only roots and, through the shared `core.security.path` rules, credential paths, persona instruction files, read-only evidence directories and the active Goal's protected paths — so a sandbox write is refused exactly when the file tools or the shell pre-flight would refuse it. Reads of those paths stay open. write/append/delete fire `trigger_destructive_action_hook` (carries `session_id` for turn/chat binding). | ✅ |
| _python_subprocess.py | Helper | Python script subprocess: sandbox wrapping, readonly_workspace context passthrough, env, timeout, output parsing; a stopped request (`context.cancel_token`) shares the timeout's exit and kills the script. Each pipe is read through `communicate_bounded` up to 12 × the wrapper's `max_output_bytes` + 64 KiB (the wrapper bounds only the stdout characters it captures and prints its result with `json.dumps`, up to 12 bytes per character), so a script that floods stderr or a file descriptor cannot grow the host's memory; when a pipe was cut, a line saying so is appended to the result's stderr. | ✅ |
| _background_spawn.py | Helper | Background process spawning with sandbox, env isolation, process groups; **PTY-first on POSIX (non-sandbox) with PIPE fallback** via `_background_pty_spawn.py`. Unless `harness_owned` (MCP servers), a job runs under the agent's capability scope (read-only workspace) and records execution evidence. A sandboxed job may use the standing granted directories (`standing_access_roots`). | ✅ |
| _background_pty_spawn.py | Helper | POSIX PTY master/slave spawn adapter (merged stdout/stderr); skipped under bwrap or on Windows. The master read side maps the Linux EIO hang-up to a clean EOF so output still buffered at child exit is never dropped. | ✅ |
