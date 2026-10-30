# tests/support/

## Overview

Pytest-only helpers, not shipped in the harness wheel: process teardown and marked-process control, a memory- and time-guarded child process and read observation, real-git and live-MCP-server fixtures, damaged FTS5 indexes, completion-guard drivers with call-record and run-context builders, and store doubles. The `test_*.py` files here test those helpers.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `browser_process_cleanup.py` | Core | Terminate automation child processes in a pytest process tree | ✅ |
| `sse_shutdown_flag.py` | Core | Reset sse-starlette's process-global shutdown flag between test uvicorn servers | ✅ |
| `mcp_testkit/` | Core | Real-server helpers for the MCP transport, TLS, launch-gate and caller-cancellation tests (see its `_ARCH.md`) | ✅ |
| `marked_processes.py` | Core | Find, wait for and remove worker processes by a marker in their command line (`process_alive` / `kill_marked` / `wait_until`; a shell that only carries the marker as script text does not count), so stop/cancel tests prove a sleeper they started is running before the stop and gone after it on any platform, without pgrep/pkill | ✅ |
| `run_context.py` | Core | `real_run_context`: the context the production `setup_workspace` builds for a workspace directory, so a test of a context reader goes red when the reader asks for a key a real run never writes (a hand-built context accepts any key) | ✅ |
| `call_records.py` | Core | Build the tool-call records the completion guard reads, one line per call (`call` / `write` / `shell` / `unit_tests` / `lint`, with the `OK` / `FAIL` / `EMPTY` levels), so a rule, checklist or guard test states the trace it is about | ✅ |
| `guarded_child.py` | Core | `run_guarded`: run a Python snippet in a child process that is killed when its resident memory passes a budget or it runs past a deadline, and report how it ended (`GuardedRun`: finished / over memory / timed out). For tests that feed the harness a hostile file (an endless device, a FIFO, a sparse multi-gigabyte file), so a regression fails as an assertion instead of exhausting memory or hanging the run | ✅ |
| `read_spy.py` | Core | `record_opened` / `record_read_sizes`: the files opened for reading (by the bounded reader or through `Path.open`) and the size argument of each bounded `read`, observed at the real file-system boundary through `monkeypatch`, for tests that pin "never opened", "opened once" and "never read whole" | ✅ |
| `git_probe.py` | Core | Real-git helpers for the hardened-argv tests: `git` / `run` / `plain` run a command or build the un-hardened control argv, `program` writes a marker-leaving script and `fired` / `clear` read and reset the markers, so "the hardened command ran nothing" is an observation made against a control that does fire | ✅ |
| `completion_guard_harness.py` | Core | Drive the completion guard the way a run does (one hook call, the middleware chain `build_middlewares` assembles, a real `create_skill_agent` run over a scripted counting model) and the policies that let a run write files or not, and the graph state holding any messages (`make_state`), so each capability test states its case and not the plumbing | ✅ |
| `shipped_graph.py` | Core | `ScriptedModel` and `shipped_agent`: the middleware stack `build_middlewares` assembles, compiled with `create_agent` around given tools over a scripted model, with `shipped_session` / `yolo_config` for the session context of a run that may use tools without asking, so a test of the stack observes what a run does (which tool calls run together, what the model is sent) and not what a mock of the framework does | ✅ |
| `fake_load_sensor.py` | Core | `FakeLoadSensor`: a maintenance load sensor that reports the level a test sets (`set_level`), shared by the scheduler and quota-integration tests | ✅ |
| `dense_vector_store.py` | Core | In-memory dense vector store double: refuses a vectorless document before writing anything and pages `scroll` by a cursor that is `None` only after the last page, so memory tests exercise the contracts a plain `AsyncMock` store hides | ✅ |
| `fts5_corruption.py` | Core | `corrupt_fts5_index` / `CORRUPTIONS`: damage an FTS5 index the way a power loss does (an emptied `_docsize` shadow table, a truncated segment block) and assert the damage is real (`integrity-check` raises `DatabaseError`), so a heal test starts from an index SQLite itself reports as malformed; `corrupt_fts5_content_page`: break the page that stores the text of an FTS5 table in the database file and assert its rows can no longer be read | ✅ |
| `fts5_legacy.py` | Core | `downgrade_fts5_tokenizer`: put an FTS5 table back on the plain `unicode61` tokenizer with plain SQL, rows and rowids kept, the way an index written without stemming looks (uses no code under test); `fts5_declaration` (the stored `CREATE` statement, which names the tokenizer) and `fts5_rows` (every row with its rowid, the fingerprint a tokenizer swap must keep) | ✅ |
| `test_dense_vector_store.py` | Unit | Unit tests for `dense_vector_store` (write refusal, read copies, cursor paging, filter shapes) | — |
| `test_browser_process_cleanup.py` | Unit | Unit tests for `browser_process_cleanup` (100% line coverage) | — |
| `test_conftest_browser_cleanup_wiring.py` | Integration | conftest hook smoke + harness/server marker parity | — |
| `test_sse_shutdown_flag.py` | Unit | Unit tests for `sse_shutdown_flag` (flag clearing + missing-flag no-op) | — |

## Key Dependencies

- `myrm_agent_harness.utils.os_compat::terminate_process_graceful`
- Invoked from `tests/conftest.py` and `tests/toolkits/browser/conftest.py` via `pytest_sessionfinish` / `atexit`
- Complements the stamp-based `toolkits.browser.doctor` orphan check (this helper reaps by process tree instead)
- Mirror copy: `myrm-agent/myrm-agent-server/tests/support/browser_process_cleanup.py` (keep markers in sync)
