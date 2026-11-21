# common/

## Overview
Common executor components.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Common executor components. | — |
| command_rewriter.py | Core | Command rewriting service: `/workspace` paths resolved to the working directory by a lexical match on the word (a directory merely called workspace, such as `~/workspace`, stays as typed; what a shell would expand first, such as a glob or a brace list, is not seen); for a POSIX shell the root is quoted wherever `core.security.shell_command_lexer` reads the match as plain text and the root holds a space, a comma or a shell metacharacter, so a folder name stays one word and never runs as code (a match inside quotes, a command with a heredoc operator and a non-POSIX shell get the root as typed); its log lines show the command masked and cut (`core.security.redact.command_preview`). | ✅ |
| error_handler.py | Core | Execution error handling decorator. | ✅ |
| exit_classify.py | Core | Non-zero exit code semantic classifier. | ✅ |
| execution_helper.py | Core | Execution helper utilities. | ✅ |
| executor_utils.py | Core | Common utility functions for code executors. | ✅ |
| file_scanner.py | Core | Generated files scanner. | ✅ |
| mcp_markers.py | Core | Shape of the stdout call marker a PTC script prints (`__MCP_DATA__{nonce}{base64}__END__{nonce}`), shared by the output scrubber and the host-side extractor. `scrub_outside_markers` lets marker-shaped spans through `ExecutionResult`'s scrubber verbatim (the credential scrubber reads the `eyJ…` payload as a JWT and truncates it); `scrub_marker_spans` scrubs the spans the host rejects. Only the shape is known here; the authenticating nonce lives in the agent layer. | ✅ |
| subprocess_guard.py | Core | Single-responsibility guard. Does NOT replace the richer timeout logic | ✅ |
| venv_manager.py | Core | Virtual environment management service with zero-network lean sandbox initialization and transparent pip command rewriting (the venv's pip path goes in quoted for the shell); `discard()` removes the venv crash-safely (atomic rename, then delete) so the next use rebuilds it empty. | ✅ |
| wrapper_async_mode.py | Core | In-sandbox execution-mode detection source spliced into the wrapper script: pure AST-based detection of a script that calls `asyncio.run` itself, or defines `async def main()` and calls it undriven. | ✅ |
| wrapper_script.py | Core | Unified execution wrapper script with zero-host-dependency inlined PEP 578 audit hook, readonly_workspace filesystem protection injection, standard main module contract, execution-mode dispatch (helpers from `wrapper_async_mode.py`; every other script is compiled with `ast.PyCF_ALLOW_TOP_LEVEL_AWAIT`, so module-level await runs as a coroutine with the script's own line numbers, string literals and name scoping), and graceful SystemExit classification. | ✅ |

## Key Dependencies

- `core/security/redact` (`command_preview` for the log lines of `command_rewriter.py` and `venv_manager.py`)
- `core/security/shell_command_lexer` (`iter_syntax_chars`: which `/workspace` matches `command_rewriter.py` finds as plain shell text)
- `utils`
- `infra.data_dir` (state root of the shared virtual environment)
