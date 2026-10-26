# cli/

## Overview
CLI runtime backend — spawns one external CLI agent process per turn (Claude Code, Codex, ...) and streams its NDJSON output as `RuntimeEvent`s. Conversations continue through the CLI's own session id: it is stored the moment the CLI announces it (Claude `system/init`, Codex `thread.started`) and replayed with the CLI's resume syntax.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Facade: lazy `CliRuntime`. The other modules are imported by their own path. | ✅ |
| dialect.py | Core | Per-CLI command-line differences (`CliDialect`): resume syntax (Claude `--resume <id>`, Codex `exec resume <id>`), native turn limit (Claude `--max-turns`), partial-message streaming; session-id shape check (`is_session_id`). A CLI without a dialect is spawned as configured. | ✅ |
| failure.py | Core | `classify_failure`: the `AcpError` of a finished attempt from the CLI's own words (`result` line: max turns / auth / rate limit; else exit code → crash); a process this runtime stopped is a cancellation, never a crash. | ✅ |
| parser.py | Internal | Event builders shared by the output formats (tool call / result with one-line summary and bounded output, usage, error, thinking, Codex `item.*` events). | ✅ |
| process.py | Core | `CliProcess` / `spawn_cli_process`: one CLI process group — line-wise stdout (16 MiB line limit), bounded stderr tail, and the only code that stops it (idempotent SIGTERM→SIGKILL, shielded from caller cancellation, runs on every exit path of the context). | ✅ |
| runtime.py | Core | `CliRuntime`: launches a turn, resumes the announced session (only from the directory that created it), retries a rejected resume once as a fresh session in the same turn, persists the announced id at once, applies a stop that lands before the process exists, and ends the turn with DONE or the one classified ERROR. | ✅ |
| session.py | Core | `CliSessionBook`: bounded memory-first CLI session records with best-effort write-through to the host `CliSessionStore` (contract and `CliSessionRecord` live in `types.py`); store failures degrade to a fresh session and never fail a turn. | ✅ |
| turn_parser.py | Core | `TurnParser`: stateful per-turn NDJSON parser (Claude content blocks / `stream_event` text deltas deduplicated against the full message, Codex `item.*`, plain text) exposing the announced session id and the CLI's own `result` verdict. | ✅ |
