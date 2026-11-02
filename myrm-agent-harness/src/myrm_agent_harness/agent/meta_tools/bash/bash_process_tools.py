"""Unified LangChain tool for background bash process management.

Single ``bash_process_tool`` manages list/output/wait/kill/stdin for jobs spawned
via ``bash_code_execute_tool(run_in_background=True)``.

[INPUT]
- agent.meta_tools.bash._tool.process_handlers::handle_list / handle_output / handle_wait / handle_kill / handle_stdin (POS: session-scoped action handlers)
- core.security.ocap::check_capability_access (POS: the active capability handle; acting on a job needs EXECUTE)
- runtime context (POS: session_id from RunnableConfig)

[OUTPUT]
- create_bash_process_tool: Unified process management tool factory
- BASH_PROCESS_TOOL_NAME: Stable tool id for spawn lifecycle tracking

[POS]
PTC-adjacent surface tool — bash-tool-package only; no business coupling. Jobs are scoped to the session,
which a delegated child shares with its delegating agent, so the actions that signal, feed or close a job
check the capability handle themselves: a read-only child observes the parent's jobs but cannot act on them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from myrm_agent_harness.agent.meta_tools.bash._tool.process_handlers import (
    OUTPUT_DEFAULT_LINES,
    handle_kill,
    handle_list,
    handle_output,
    handle_stdin,
    handle_wait,
)
from myrm_agent_harness.core.security.ocap import CapabilityAction, check_capability_access
from myrm_agent_harness.utils.locale import is_chinese

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

BASH_PROCESS_TOOL_NAME = "bash_process_tool"

_OUTPUT_MAX_LINES = 500
_WAIT_DEFAULT_SECONDS = 30
_WAIT_MAX_SECONDS = 120

_BASH_PROCESS_ACTIONS = Literal[
    "list",
    "output",
    "kill",
    "wait",
    "write_stdin",
    "submit_stdin",
    "close_stdin",
]

# The actions that only read a job. Every other action signals, feeds or closes it (the approval layer maps
# them to ``shell_exec``, see ``resolve_permission_type``), so it needs the EXECUTE capability that
# ``bash_code_execute_tool`` needs to start a job; an action added later is gated until it is listed here.
_OBSERVING_ACTIONS = frozenset({"list", "output", "wait"})

_MISSING_SESSION_PAYLOAD: dict[str, object] = {
    "content": (
        "Background process tools require a bound session_id. "
        "This protects multi-tenant isolation: a missing session_id would "
        "otherwise surface processes from other chats."
    ),
    "metadata": {"error": "missing_session_id"},
}


def _extract_session_id(config: RunnableConfig) -> str | None:
    from myrm_agent_harness.agent.context_management.context import (
        extract_context_from_runnable_config,
    )

    ctx = extract_context_from_runnable_config(config)
    sid = ctx.get("session_id")
    return str(sid) if sid else None


class _BashProcessInput(BaseModel):
    action: _BASH_PROCESS_ACTIONS = Field(
        description=(
            "list: all background jobs in this session (includes last_progress when available); "
            "output: tail stdout/stderr for pid; if waiting_for_input=true read input_wait_hint "
            "and use submit_stdin (do not blind-poll); "
            "wait: block until pid exits or timeout_seconds (max 120); if still_running with "
            "waiting_for_input=true use submit_stdin; "
            "kill: stop pid (SIGTERM unless force=true); "
            "write_stdin: send raw bytes to pid stdin (no newline); "
            "submit_stdin: send data plus Enter (for y/n prompts); "
            "close_stdin: send EOF to close stdin."
        ),
    )
    pid: int | None = Field(
        default=None,
        description=(
            "Required for output, wait, kill, and stdin actions. "
            "MUST be the integer pid returned by list/output as the 'pid' field — "
            "do not pass a string like '97e6d410' (that is a job id, not a pid)."
        ),
        ge=1,
    )
    max_lines: int = Field(
        default=OUTPUT_DEFAULT_LINES,
        description=f"For output: tail size per stream (1-{_OUTPUT_MAX_LINES}).",
        ge=1,
        le=_OUTPUT_MAX_LINES,
    )
    since_cursor: int | None = Field(
        default=None,
        description=("For output: monotonic cursor from a previous next_cursor for incremental polling."),
    )
    timeout_seconds: int = Field(
        default=_WAIT_DEFAULT_SECONDS,
        description=f"For wait: seconds to block (1-{_WAIT_MAX_SECONDS}). Returns still_running on timeout.",
        ge=1,
        le=_WAIT_MAX_SECONDS,
    )
    force: bool = Field(
        default=False,
        description="For kill: send SIGKILL when true, else SIGTERM first.",
    )
    filter: str | None = Field(
        default=None,
        description=(
            "For output: optional regex applied per line (e.g. 'ERROR|WARN') — only matching stdout/stderr lines are returned."
        ),
    )
    data: str = Field(
        default="",
        description=(
            "For write_stdin/submit_stdin: text to send to the process stdin (e.g. 'y' to confirm an installer prompt)."
        ),
    )


_BASH_PROCESS_TOOL_DESCRIPTION_EN = (
    "Manage background bash processes started with bash_code_execute_tool(run_in_background=true). "
    "When output or wait returns waiting_for_input=true, read input_wait_hint and answer with "
    "submit_stdin (do not blind-poll). "
    "Actions: list (session jobs + last_progress), output (tail/incremental poll via since_cursor), "
    "wait (block until exit or timeout_seconds, max 120), kill (SIGTERM or force SIGKILL), "
    "write_stdin (raw stdin), submit_stdin (stdin + Enter), close_stdin (EOF)."
)

_BASH_PROCESS_TOOL_DESCRIPTION_ZH = (
    "管理通过 bash_code_execute_tool(run_in_background=true) 启动的后台进程。"
    "当 output 或 wait 返回 waiting_for_input=true 时，根据 input_wait_hint 使用 submit_stdin 响应（切勿盲目轮询）。"
    "操作：list（会话任务与进度），output（查看增量输出/配合 since_cursor 轮询），"
    "wait（阻塞等待结束或超时，最大 120s），kill（默认 SIGTERM，force 时发送 SIGKILL），"
    "write_stdin（原始 stdin），submit_stdin（stdin+换行），close_stdin（EOF）。"
)


def resolve_bash_process_tool_description(locale: str | None = None) -> str:
    """Resolve LLM-facing bash_process_tool description."""
    if is_chinese(locale):
        return _BASH_PROCESS_TOOL_DESCRIPTION_ZH
    return _BASH_PROCESS_TOOL_DESCRIPTION_EN


def create_bash_process_tool(locale: str | None = None) -> BaseTool:
    """Return the unified background process management tool."""

    @tool(
        BASH_PROCESS_TOOL_NAME,
        description=resolve_bash_process_tool_description(locale),
        args_schema=_BashProcessInput,
    )
    async def _bash_process(
        action: _BASH_PROCESS_ACTIONS,
        pid: int | None = None,
        max_lines: int = OUTPUT_DEFAULT_LINES,
        since_cursor: int | None = None,
        timeout_seconds: int = _WAIT_DEFAULT_SECONDS,
        force: bool = False,
        filter: str | None = None,
        data: str = "",
        *,
        config: RunnableConfig,
    ) -> dict[str, object]:
        session_id = _extract_session_id(config)
        if session_id is None:
            return _MISSING_SESSION_PAYLOAD

        if action not in _OBSERVING_ACTIONS and not check_capability_access(CapabilityAction.EXECUTE):
            return {
                "content": f"action={action!r} is not permitted: this agent holds no execute capability.",
                "metadata": {"error": "capability_denied", "action": action},
            }

        if action == "list":
            return await handle_list(session_id)

        pid_required = {
            "output",
            "kill",
            "wait",
            "write_stdin",
            "submit_stdin",
            "close_stdin",
        }
        if action in pid_required and pid is None:
            return {
                "content": f"action={action!r} requires pid.",
                "metadata": {"error": "missing_pid", "action": action},
            }

        if action == "output":
            assert pid is not None
            return await handle_output(session_id, pid, max_lines, since_cursor, filter)
        if action == "wait":
            assert pid is not None
            return await handle_wait(session_id, pid, timeout_seconds)
        if action == "kill":
            assert pid is not None
            return await handle_kill(session_id, pid, force)
        if action == "write_stdin":
            assert pid is not None
            return await handle_stdin(
                session_id,
                pid,
                data,
                append_newline=False,
                close=False,
                action=action,
            )
        if action == "submit_stdin":
            assert pid is not None
            return await handle_stdin(
                session_id,
                pid,
                data,
                append_newline=True,
                close=False,
                action=action,
            )
        if action == "close_stdin":
            assert pid is not None
            return await handle_stdin(
                session_id,
                pid,
                "",
                append_newline=False,
                close=True,
                action=action,
            )

        return {
            "content": ("Unknown action. Use list, output, wait, kill, write_stdin, submit_stdin, or close_stdin."),
            "metadata": {"error": "invalid_action"},
        }

    return _bash_process


__all__ = [
    "BASH_PROCESS_TOOL_NAME",
    "create_bash_process_tool",
]
