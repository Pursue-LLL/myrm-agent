# runtime/

## Overview
ACP Runtime backends — unified interface for ACP and CLI agents.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | ACP Runtime backends — unified interface for ACP and CLI agents. | ✅ |
| _base.py | Internal | Base class for RuntimeBackend implementations — timeout control, truncation, error handling; `build_safe_env` gives a child process only the core variables (shared `CORE` policy of `code_execution/security/env_isolation.py`) plus its CLI's login-home variable, then the configured `env` by `auth_mode`; the turn generator is closed with `aclosing`, so a timeout, a failure or an abandoned stream stops the backend process. | ✅ |
| acp_callback.py | Core | ACP callback handler for the AcpRuntime backend. | ✅ |
| acp_runtime.py | Core | ACP protocol runtime backend — session reuse, cancel, resume; prompt failures re-raise to surface as ERROR; `session/close` is sent only when `initialize` advertised `sessionCapabilities.close` and is bounded (4s), so a silent agent cannot skip the transport teardown that terminates its process. | ✅ |
| cli/ | Core | CLI runtime sub-package: `CliRuntime` (one CLI agent process per turn), per-CLI dialects, process ownership, NDJSON turn parsing, failure classification, `CliSessionBook` (CLI session continuity). See [cli/_ARCH.md](cli/_ARCH.md). | ✅ |
| pool.py | Core | Runtime pool: multi-backend management, concurrency control (global semaphore + per-backend serialization), config MCP passthrough gated by backend `supports_mcp` capability. A `oneshot` turn runs on a private backend (fresh session, closed afterwards, registered for `cancel` / `close_all`), so it never touches the shared backend's persistent session or process. `release_resident()` stops only the resident (ACP) backends and keeps CLI backends with their `--resume` ids, so a host can reclaim idle processes without ending CLI sessions. An optional `cli_session_store` is handed only to the shared persistent backends (never to oneshot private backends), so CLI sessions also survive a restart of the host process. No periodic liveness supervision: a resident ACP process that exited is reconnected by its next `run_turn`, and a CLI backend has no process between turns by design. | ✅ |
