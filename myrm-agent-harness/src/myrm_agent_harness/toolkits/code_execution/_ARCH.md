# code_execution/

## Overview
Code execution toolkit entry point. Aggregates execution configuration, executor implementations, and the **PTC family SSOT** (MCP PTC + DW PTC — see [EXECUTION_SYSTEM.md § PTC 家族](EXECUTION_SYSTEM.md#ptc-家族programmatic-tool-calling)).

Detailed design: [EXECUTION_SYSTEM.md](EXECUTION_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Code execution toolkit entry point. Aggregates execution configuration, executor implementations, | ✅ |
| config.py | Config | Code execution configuration layer. Defines execution modes, network policies, and runtime settings | ✅ |
| code_detector.py | Core | Python vs Bash code type detector. Delegates ``python -c`` extraction to ``python_extractor`` SSOT. ``runs_as_python`` repeats the executor's routing (strip, unwrap one Markdown fence, detect; a background spawn is always a shell) so guards that only make sense for shell syntax stand down exactly when no shell reads the text. | ✅ |
| env_probe.py | Core | Python toolchain probe. Detects python3/pip/PEP-668/uv status; consumed by bash_code_execute_tool.py (tool description) and platform.py (`<environment>` system prompt tag). Cache keyed by `(PATH, VIRTUAL_ENV)` so a lookup line always describes the current environment; interpreter probes run concurrently under a short per-probe ceiling, and a probe that times out yields silence rather than a false "missing". | ✅ |
| factory.py | Core | Code executor factory. Creates LocalExecutor for in-container code execution based on configuration. | ✅ |
| interceptor.py | Core | ExecutionInterceptor Protocol — hooks before sandbox actions a file rollback cannot fully undo (file write, rm, sed, and shell commands with external effects) | ✅ |
| platform.py | Core | Cross-platform runtime detection, shell configuration, and unified `<environment>` system prompt tag (OS + Shell + Python toolchain + VNC visual desktop). | ✅ |
| python_extractor.py | Core | Quote-aware Python extraction from bash commands; pipe stdin + ``cat *.py | python3`` feeder path extraction; heredoc unwrap for MCP PTC bash (``python3 <<EOF``, ``python3 - <<EOF``, and ``cat > path <<EOF`` / ``cat <<EOF > path`` alone or after ``cd ... &&``); SSOT for code_detector, SkillExecutor, PTC verifier, preflight guards. `validate_python_syntax` reports the line and column and quotes the offending line (cut to 160 characters around the column). | ✅ |
| saved_script.py | Core | `resolve_saved_script`: reads the workspace file that a plain `[cd <workspace root> &&] python[3] <file>.py` command runs (no flags, arguments, pipes, env prefix or other directory; a regular UTF-8 file of at most `MAX_SAVED_SCRIPT_BYTES` whose symlink-resolved path lies inside the root), else `None`. `SavedScript.launcher(source)` builds the code that runs the source in-process as `__main__` in a fresh namespace of its own (`sys.argv`, `sys.path[0]`, `__file__` as under `python file.py`, compiled with the file name so tracebacks name the real file and line). Lets a saved script that imports MCP skills get the skill runtime that a child shell cannot give it. | ✅ |
| git_digest.py | Core | Git repository history & change digest extractor. Extracts branch, dirty state, and recent commit summaries in milliseconds. | ✅ |
| sandbox_snapshot.py | Core | Sandbox bootstrap snapshot generator. Captures initial workspace state, git status, language runtimes, and package managers into compact XML. A runtime is listed only when its binary ran and reported a version (a toolchain proxy with nothing installed or a launcher stub is left out, `python` is tried when `python3` does not run, Java's version is read from `java -version` on stderr); package managers and CLI tools are listed by presence on PATH. It starts up to ten processes in turn (three git commands and one version command per runtime binary found, up to seven; the `git config` listing behind the status command is capped at 5 s, the others at 1 s, 14 s in all for an ordinary repository layout), so call it from a thread and bound the wait, as the workspace-rules middleware does. A working tree whose status could not be read (refused layout, timeout, git missing) is reported as `unknown`, never `clean`. Command output is decoded with `errors="replace"`, so a branch or path that is not valid UTF-8 shows as `U+FFFD` instead of failing the snapshot. Top-level entry names are third-party text: rendered as one line of plain text by `core/security/detection/display_name.py` (control and bidirectional characters become spaces, framing markers neutralised, instruction-like names withheld, 80 characters at most). The `Guidance` line tells the model the Git state and file list date from the start of the conversation. | ✅ |

| Submodule | Description |
|-----------|-------------|
| executors/ | Executors module for Agent-in-Sandbox mode. |
| ptc/ | **DW PTC** — Workflow RPC；LLM 脚本经 UDS/TCP 调 spawn/notify。MCP PTC 见 EXECUTION_SYSTEM § PTC 家族。 |
| sandbox/ | OS-level process sandbox for local/desktop execution. |
| security/ | Execution security — shell command analysis, blacklists, and validators. |
| session/ | Persistent Session Module (with Auto-Tee, OOM & Disk Quota protection) |
| tool_discovery/ | CLI tool auto-discovery module entry point. Provides get_cli_tools_context() one-stop API to detect |
| utils/ | Code execution utilities. |
| workspace/ | Session workspaces rooted at explicit host-provided aggregate directory (`merged_context[\"workspaces_storage_root\"]` consumed by Harness `WorkspaceService`). |
