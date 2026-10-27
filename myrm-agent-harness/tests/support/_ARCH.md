# tests/support/

## Overview

Pytest-only helpers for harness test teardown, local dev hygiene, live MCP transport tests, and store doubles. Not shipped in the harness wheel.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `browser_process_cleanup.py` | Core | Terminate automation child processes in a pytest process tree | ✅ |
| `sse_shutdown_flag.py` | Core | Reset sse-starlette's process-global shutdown flag between test uvicorn servers | ✅ |
| `mcp_live_server.py` | Core | Real uvicorn-hosted MCP servers (SSE / streamable HTTP, optionally TLS or mTLS) on pre-bound loopback ports, exposing echo/add tools and optional `initialize` instructions; single bootstrap shared by every live transport test | ✅ |
| `mcp_tls_pki.py` | Core | Throwaway PKI (private CA, rogue CA, server leaf, plain and passphrase-encrypted client leaf) whose chains satisfy Python 3.13 strict X.509 verification, plus the TLS-rejection error-text markers | ✅ |
| `mcp_launch_gates.py` | Core | Patch targets and `RecordingTrustGate` for the stdio launch gates (workspace trust + OSV malware check) shared by actor and enumeration tests | ✅ |
| `marked_processes.py` | Core | Find, wait for and remove worker processes by a marker in their command line (`process_alive` / `kill_marked` / `wait_until`; a shell that only carries the marker as script text does not count), so stop/cancel tests prove a sleeper they started is running before the stop and gone after it on any platform, without pgrep/pkill | ✅ |
| `run_context.py` | Core | `real_run_context`: the context the production `setup_workspace` builds for a workspace directory, so a test of a context reader goes red when the reader asks for a key a real run never writes (a hand-built context accepts any key) | ✅ |
| `call_records.py` | Core | Build the tool-call records the completion guard reads, one line per call (`call` / `write` / `shell` / `unit_tests` / `lint`, with the `OK` / `FAIL` / `EMPTY` levels), so a rule, checklist or guard test states the trace it is about | ✅ |
| `completion_guard_harness.py` | Core | Drive the completion guard the way a run does (one hook call, the middleware chain `build_middlewares` assembles, a real `create_skill_agent` run over a scripted counting model) and the policies that let a run write files or not, and the graph state holding any messages (`make_state`), so each capability test states its case and not the plumbing | ✅ |
| `dense_vector_store.py` | Core | In-memory dense vector store double: refuses a vectorless document before writing anything and pages `scroll` by a cursor that is `None` only after the last page, so memory tests exercise the contracts a plain `AsyncMock` store hides | ✅ |
| `test_dense_vector_store.py` | Unit | Unit tests for `dense_vector_store` (write refusal, read copies, cursor paging, filter shapes) | — |
| `test_browser_process_cleanup.py` | Unit | Unit tests for `browser_process_cleanup` (100% line coverage) | — |
| `test_conftest_browser_cleanup_wiring.py` | Integration | conftest hook smoke + harness/server marker parity | — |
| `test_sse_shutdown_flag.py` | Unit | Unit tests for `sse_shutdown_flag` (flag clearing + missing-flag no-op) | — |

## Key Dependencies

- `myrm_agent_harness.utils.os_compat::terminate_process_graceful`
- Invoked from `tests/conftest.py` and `tests/toolkits/browser/conftest.py` via `pytest_sessionfinish` / `atexit`
- Complements the stamp-based `toolkits.browser.doctor` orphan check (this helper reaps by process tree instead)
- Mirror copy: `myrm-agent/myrm-agent-server/tests/support/browser_process_cleanup.py` (keep markers in sync)
