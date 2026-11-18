"""Unified LangChain tool for background bash process management.

Single ``bash_process_tool`` manages list/output/wait/kill/stdin for jobs spawned
via ``bash_code_execute_tool(run_in_background=True)``.

[INPUT]
- agent.meta_tools.bash._tool.process_handlers::handle_list / handle_output / handle_wait / handle_kill / handle_stdin (POS: session-scoped action handlers)
- agent.meta_tools.bash._background.types::OUTPUT_RING_LINES / WAIT_MAX_SECONDS / INPUT_WAIT_IDLE_SECONDS (POS: the limits the schema and the descriptions state)
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

from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    INPUT_WAIT_IDLE_SECONDS,
    OUTPUT_RING_LINES,
    WAIT_MAX_SECONDS,
)
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

_WAIT_DEFAULT_SECONDS = 30
_IDLE_SECONDS = int(INPUT_WAIT_IDLE_SECONDS)

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
    "content": "Background process tools are unavailable: no session_id is bound to this call.",
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
            "output: tail stdout/stderr for pid; "
            f"wait: block until pid exits or timeout_seconds (max {WAIT_MAX_SECONDS}); "
            "kill: stop pid (SIGTERM, then SIGKILL; force=true: SIGKILL at once); "
            "write_stdin: send raw bytes to pid stdin (no newline); "
            "submit_stdin: send data plus Enter (for y/n prompts); "
            "close_stdin: send EOF to close stdin."
        ),
    )
    pid: int | None = Field(
        default=None,
        description=(
            "Required for output, wait, kill, and stdin actions. "
            "MUST be the integer pid (from the start message, list or output), not the job_id: "
            "do not pass a string like '97e6d410'."
        ),
        ge=1,
    )
    max_lines: int = Field(
        default=OUTPUT_DEFAULT_LINES,
        description=f"For output: tail size per stream (1-{OUTPUT_RING_LINES}).",
        ge=1,
        le=OUTPUT_RING_LINES,
    )
    timeout_seconds: int = Field(
        default=_WAIT_DEFAULT_SECONDS,
        description=f"For wait: seconds to block (1-{WAIT_MAX_SECONDS}). Returns still_running on timeout.",
        ge=1,
        le=WAIT_MAX_SECONDS,
    )
    force: bool = Field(
        default=False,
        description="For kill: send SIGKILL when true, else SIGTERM first.",
    )
    data: str = Field(
        default="",
        description=(
            "For write_stdin/submit_stdin: text to send to the process stdin (e.g. 'y' to confirm an installer prompt)."
        ),
    )


_BASH_PROCESS_TOOL_DESCRIPTION_EN = (
    "Manage background bash processes started with bash_code_execute_tool(run_in_background=true) "
    "or auto-detached by it after yield_after_seconds. "
    "Actions: list (session jobs + last_progress), output (tail of stdout/stderr, returns immediately), "
    f"wait (block until exit or timeout_seconds, max {WAIT_MAX_SECONDS}), "
    "kill (SIGTERM, then SIGKILL if it does not exit; force=true sends SIGKILL at once), "
    "write_stdin (raw stdin), submit_stdin (stdin + Enter), close_stdin (EOF). "
    f"waiting_for_input=true only means no output for {_IDLE_SECONDS} s while stdin is open: "
    "the job may be waiting for input or just quiet. "
    "If the command is expected to prompt or its latest output asks a question, "
    "answer with submit_stdin; otherwise ignore the flag."
)

_BASH_PROCESS_TOOL_DESCRIPTION_ZH = (
    "管理通过 bash_code_execute_tool(run_in_background=true) 启动、"
    "或在 yield_after_seconds 后被它自动转入后台的后台进程。"
    "操作：list（会话任务与 last_progress），output（stdout/stderr 末尾，立即返回），"
    f"wait（阻塞等待结束或达到 timeout_seconds，最大 {WAIT_MAX_SECONDS} 秒），"
    "kill（先发 SIGTERM，不退出则升级为 SIGKILL；force=true 直接发 SIGKILL），"
    "write_stdin（原始 stdin），submit_stdin（stdin+回车），close_stdin（EOF）。"
    f"waiting_for_input=true 只表示 stdin 仍开着且已 {_IDLE_SECONDS} 秒无输出：任务要么在等输入，要么只是安静。"
    "命令本应提问、或最新输出是个问句时，用 submit_stdin 应答；否则忽略该标记。"
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
        timeout_seconds: int = _WAIT_DEFAULT_SECONDS,
        force: bool = False,
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
            return await handle_output(session_id, pid, max_lines)
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
