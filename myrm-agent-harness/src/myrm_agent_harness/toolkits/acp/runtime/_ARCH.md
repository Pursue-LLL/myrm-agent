# runtime/

## Overview
ACP Runtime backends — unified interface for ACP and CLI agents.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | ACP Runtime backends — unified interface for ACP and CLI agents. | ✅ |
| _base.py | Internal | Base class for RuntimeBackend implementations — timeout control, truncation, error handling with process cleanup on timeout/failure. | ✅ |
| _parser.py | Internal | Shared NDJSON event parsers for CLI runtimes. | ✅ |
| _spawn_hints.py | Internal | Bare CLI spawn failure hints for CliRuntime error messages. | ✅ |
| acp_callback.py | Core | ACP callback handler for the AcpRuntime backend. | ✅ |
| acp_runtime.py | Core | ACP protocol runtime backend — session reuse, cancel, resume; prompt failures re-raise to surface as ERROR (matching CLI); `session/close` is sent only when `initialize` advertised `sessionCapabilities.close` and is bounded (4s), so a silent agent cannot skip the transport teardown that terminates its process. | ✅ |
| cli_runtime.py | Core | CLI runtime backend — spawns a CLI agent process, resolves launch and permission-mode args via the auth profile registry, and parses NDJSON output. | ✅ |
| pool.py | Core | Runtime pool: multi-backend management, concurrency control (global semaphore + per-backend serialization), config MCP passthrough gated by backend `supports_mcp` capability. A `oneshot` turn runs on a private backend (fresh session, closed afterwards, registered for `cancel` / `close_all`), so it never touches the shared backend's persistent session or process. `release_resident()` stops only the resident (ACP) backends and keeps CLI backends with their `--resume` ids, so a host can reclaim idle processes without ending CLI sessions. No periodic liveness supervision: a resident ACP process that exited is reconnected by its next `run_turn`, and a CLI backend has no process between turns by design. | ✅ |
