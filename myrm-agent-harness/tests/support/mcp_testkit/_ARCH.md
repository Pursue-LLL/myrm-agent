# tests/support/mcp_testkit/

## Overview

Pytest-only helpers that run real MCP servers and launch gates for the transport, TLS, launch-gate and caller-cancellation tests. Not shipped in the harness wheel.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `live_server.py` | Core | Real uvicorn-hosted MCP servers (SSE / streamable HTTP, optionally TLS or mTLS) on pre-bound loopback ports, exposing echo/add tools and optional `initialize` instructions; single bootstrap shared by every live transport test | ✅ |
| `tls_pki.py` | Core | Throwaway PKI (private CA, rogue CA, server leaf, plain and passphrase-encrypted client leaf) whose chains satisfy Python 3.13 strict X.509 verification, plus the TLS-rejection error-text markers | ✅ |
| `launch_gates.py` | Core | Patch targets and `RecordingTrustGate` for the stdio launch gates (workspace trust + OSV malware check) shared by actor and enumeration tests | ✅ |
| `cancel_probe_server.py` | Core | Real MCP server (runnable as a stdio script, importable for HTTP) whose `slow` tool writes `started` and, when the server cancels it, `cancelled` marker files, plus a `fast` tool; lets caller-cancellation tests prove the cancel reached the server over every transport | ✅ |

## Key Dependencies

- `uvicorn`, `mcp.server.mcpserver`, `cryptography` (real listeners, protocol servers, certificate material)
- `tests.support.sse_shutdown_flag::reset_sse_shutdown_flag` (per-server teardown)
- Used by `tests/toolkits/mcp/`; `cancel_probe_server.py` is also launched as a stdio script, so it imports only the standard library and `mcp`
