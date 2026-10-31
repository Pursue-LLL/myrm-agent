# session/

## Overview
Persistent Session Module — Maintains long-running shell processes that preserve
state (env vars, cwd) across commands.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports all public API | — |
| models.py | Core | `SessionState`, `SessionExecutionResult`, `SessionConfig` (carries the run's `readonly_workspace` / `allow_network` / `granted_roots`, from which the shell's sandbox policy is built), `CommandEnv` — the session's value types; `CommandEnv` is what one command may read (`sticky` settings kept for later commands, `scoped` credentials cleared after the command) | ✅ |
| persistent_session.py | Core | Abstract `PersistentSession` base class (with `CommandStreamMixin`): state machine, `execute` (a request already stopped never starts its command), auto-recovery, shield-protected cleanup; startup orphan GC via `sweep_stale_materialized_scripts`; `_discard_shell()` (kill the process tree → TERMINATED, so the next command gets a fresh shell) | ✅ |
| command_stream.py | Core | `CommandStreamMixin`: the streaming command run — per-command random markers + `bash -n` syntax gate + script materialization armor with `is_armored` metadata propagation; one deadline (`asyncio.timeout`) that a timeout and a stopped request (`cut_deadline_on_cancel`) share, so both end through the same exit; wedge self-heal (timeout / cancel / corrupted boundary → discard the shell); `CANCELLED_*` results keep partial output and carry exit code 130; builds the `ValueMasker` of the command's `scoped` credentials (each with its URL-percent-encoded and JSON-escaped form, `printed_forms`) for both read loops | ✅ |
| process_tree.py | Core | `kill_process_tree`: ends a shell and everything it started (descendants snapshotted via psutil and terminated before the shell, then killed after a grace period) — a sandboxed shell shares the server's process group, so killing the group is not an option there; own-group shells keep the SIGTERM→SIGKILL group kill and, from a descendant snapshot taken first, also stop children that left the group (`setsid`); a shell that is already reaped is never signalled (its PID may belong to someone else by now); Windows ends the tree at once with `taskkill /F /T`, without a grace period | ✅ |
| local_session.py | Core | `LocalPersistentSession` concrete implementation with bwrap sandbox support and strict child process credential token isolation via `sanitize_env`; when a sandbox is active it builds its policy from `SessionConfig` through `build_workspace_sandbox_policy` (a session without a sandbox builds none and judges nothing) | ✅ |
| shell_flavor.py | Core | Platform-specific shell drivers: `BashFlavor` (with `exit()` interceptor + block-rc wrapper + errexit `EXIT` trap + ANSI-C `$'…'` env quoting), `PowerShellFlavor` (with UTF-8 console I/O encoding, `$ProgressPreference='SilentlyContinue'`, `exit()` interceptor, dual exit code normalization, env values always a quoted literal), `WindowsFlavor` (legacy cmd.exe fallback); every flavor sets a command's `CommandEnv` before the command and unsets its `scoped` part after the end marker | ✅ |
| stream_output_processor.py | Core | `StreamOutputProcessor` — unified tee writing (raw), SSE throttle/valve, disk quota; scrubs the live (SSE) text on whole lines of the accumulated output, holding an unfinished line or open key block (up to a size cap) so a secret split across reads is matched in one piece | ✅ |
| stream_buffer.py | Core | `ExecutionStreamBuffer` — zero-copy byte stream parsing with marker detection; `parse_failed` flag when the exit-code field is not a number (boundary corruption); with a `ValueMasker` the decoded text is masked before it is retained or returned, so the result, the tee file and the live stream all derive from masked text | ✅ |
| value_masker.py | Core | `ValueMasker` — exact-value masking of a command's credentials (`CommandEnv.scoped`) in its output, wherever the reads were cut (a read ending in the beginning of a value is held until the next read); values under 4 characters are left alone; `printed_forms` expands a credential into the value plus the forms a client prints it in (percent-encoded as in a URL, with and without escaping `!'()*`; escaped as in a JSON string; only where they differ) | ✅ |
| log_distiller.py | Core | High-efficiency terminal execution log distiller (`DistilledLogResult`, `TerminalLogDistiller`, `distill_terminal_output`) | ✅ |

## Key Dependencies

- `utils.text_utils.strip_ansi` — ANSI escape sequence stripping for clean SSE output
- `executors.common.exit_classify` — Non-zero exit code semantic classification
- `executors.models.scrub_sensitive_info` — path and credential scrubbing for real-time SSE streams (called by `StreamOutputProcessor`)
- `security.script_armor.prepare_armored_command` — Script materialization & subprocess invocation armor
- `security.script_armor.sweep_stale_materialized_scripts` — Stale orphan temporary script cleanup on startup
- `utils.runtime.cancel_hook::cut_deadline_on_cancel` — brings the command deadline forward when the request's cancel token fires
- `psutil` (core dependency) — descendant discovery for `kill_process_tree`
