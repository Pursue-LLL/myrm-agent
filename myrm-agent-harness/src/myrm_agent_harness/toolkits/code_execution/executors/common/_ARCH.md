# common/

## Overview
Common executor components.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Common executor components. | — |
| command_rewriter.py | Core | Command rewriting service: `/workspace` paths resolved to the working directory by a lexical match on the word (a directory merely called workspace, such as `~/workspace`, stays as typed; what a shell would expand first, such as a glob or a brace list, is not seen); its log lines show the command masked and cut (`core.security.redact.command_preview`). | ✅ |
| error_handler.py | Core | Execution error handling decorator. | ✅ |
| exit_classify.py | Core | Non-zero exit code semantic classifier. | ✅ |
| execution_helper.py | Core | Execution helper utilities. | ✅ |
| executor_utils.py | Core | Common utility functions for code executors. | ✅ |
| file_scanner.py | Core | Generated files scanner. | ✅ |
| mcp_markers.py | Core | Shape of the stdout call marker a PTC script prints (`__MCP_DATA__{nonce}{base64}__END__{nonce}`), shared by the output scrubber and the host-side extractor. `scrub_outside_markers` lets marker-shaped spans through `ExecutionResult`'s scrubber verbatim (the credential scrubber reads the `eyJ…` payload as a JWT and truncates it); `scrub_marker_spans` scrubs the spans the host rejects. Only the shape is known here; the authenticating nonce lives in the agent layer. | ✅ |
| subprocess_guard.py | Core | Single-responsibility guard. Does NOT replace the richer timeout logic | ✅ |
| venv_manager.py | Core | Virtual environment management service with zero-network lean sandbox initialization and transparent pip command rewriting; `discard()` removes the venv crash-safely (atomic rename, then delete) so the next use rebuilds it empty and cancels a build still running for it; `get_python_executable()` is single-flight per manager, so concurrent callers (the executor's warm-up and the first Python run) share one creation. The venv is built by the stock `python -m venv` (pip included) whose output goes to an unlinked temp file rather than a pipe, so the command finishes on its own even when the process that started it exits; the manager hands the interpreter out as soon as the command has linked it (`bin/python`, `python3`, `python3.N`, polled every 10 ms) and a background task waits for the rest, so a Python run starts at once instead of waiting seconds for pip. `ensure_pip_ready_for(text)` makes a command or snippet that names pip (`mentions_pip`) first await the venv's creation (it starts it when none is under way) and then that task, and a failed build falls back to the system interpreter without touching the directory, because processes that start together run the same command on the same path and a failing one must not remove what another still builds. | ✅ |
| wrapper_script.py | Core | Unified execution wrapper script with zero-host-dependency inlined PEP 578 audit hook, readonly_workspace filesystem protection injection, standard main module contract, pure AST-based async runner detection, and graceful SystemExit classification. | ✅ |

## Key Dependencies

- `core/security/redact` (`command_preview` for the log lines of `command_rewriter.py` and `venv_manager.py`)
- `utils`
- `infra.data_dir` (state root of the shared virtual environment)
