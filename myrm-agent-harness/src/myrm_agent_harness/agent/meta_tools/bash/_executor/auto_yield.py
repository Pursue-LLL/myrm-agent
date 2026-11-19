"""Auto-yield foreground whitelist commands into background after a short wait window.

[INPUT]
- agent.goals.wait_background_bash::is_wait_eligible_command (POS: build/test whitelist SSOT)
- .._background.registry::get_background_registry (POS: poll output and the unfinished last line)

[OUTPUT]
- DEFAULT_YIELD_AFTER_SECONDS: Profile-aligned default when arg omitted
- build_auto_yield_return: Compose tool payload after yield window (a note of the lines left out and the log that holds them, the output lines, then the unfinished last line of a job still running)

[POS]
Bash-tool helper — keeps bash_code_execute_tool aggregate root thin.
"""

from __future__ import annotations

import asyncio
import time

from myrm_agent_harness.agent.goals.wait_background_bash import is_wait_eligible_command
from myrm_agent_harness.agent.meta_tools.bash._background.registry import (
    BackgroundProcessRegistry,
    get_background_registry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import BackgroundProcessInfo, OutputTail

DEFAULT_YIELD_AFTER_SECONDS = 10
_POLL_INTERVAL_SECONDS = 0.25


def resolve_yield_seconds(yield_after_seconds: int | None) -> int | None:
    """Return effective yield window for whitelist commands, or None when disabled."""
    if yield_after_seconds == 0:
        return None
    if yield_after_seconds is not None:
        return max(1, yield_after_seconds)
    return DEFAULT_YIELD_AFTER_SECONDS


def should_auto_yield(*, command: str, run_in_background: bool, yield_after_seconds: int | None) -> bool:
    """True when a whitelist command should use the auto-yield background path."""
    if run_in_background:
        return False
    if not is_wait_eligible_command(command):
        return False
    return resolve_yield_seconds(yield_after_seconds) is not None


async def wait_for_yield_window(
    registry: BackgroundProcessRegistry,
    pid: int,
    *,
    yield_seconds: int,
) -> BackgroundProcessInfo | None:
    """Block until yield deadline or the background job exits."""
    deadline = time.monotonic() + float(yield_seconds)
    info: BackgroundProcessInfo | None = None
    while time.monotonic() < deadline:
        info = registry.get(pid)
        if info is None:
            return None
        if info.status != "running":
            return info
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    return registry.get(pid)


def _omitted_note(streams: OutputTail) -> str:
    """The line that tells the model how many lines the receipt leaves out and where the whole output is, or ``""``."""
    omitted = streams.get("omitted_lines", 0)
    if not omitted:
        return ""
    count = f"{omitted} line" if omitted == 1 else f"{omitted} lines"
    log_file = streams.get("log_file")
    where = f" Full output: {log_file} (read it with file_read_tool)" if log_file else ""
    return f"[Earlier {count} not shown.{where}]"


def build_auto_yield_return(
    *,
    info: BackgroundProcessInfo,
    yield_seconds: int,
    registry: BackgroundProcessRegistry | None = None,
) -> dict[str, object]:
    """Return tool payload after the yield window (completed early or still running)."""
    reg = registry or get_background_registry()
    streams = reg.get_output(info.pid, max_lines=50)
    stdout_text = "\n".join(streams["stdout"])
    stderr_text = "\n".join(streams["stderr"])
    note = _omitted_note(streams)

    if info.status != "running":
        parts = [f"Command finished during auto-yield window (pid={info.pid})."]
        if note:
            parts.append(note)
        if stdout_text:
            parts.append(stdout_text)
        if stderr_text:
            parts.append(f"[stderr]\n{stderr_text}")
        if info.exit_code is not None:
            parts.append(f"[exit_code: {info.exit_code}]")
        return {
            "content": "\n".join(parts),
            "metadata": {
                "auto_yielded": True,
                "completed_in_yield_window": True,
                "pid": info.pid,
                "exit_code": info.exit_code,
            },
        }

    hint = (
        f"Command still running after {yield_seconds}s — detached as background job.\n"
        f"  pid: {info.pid}\n"
        f"  command: {info.command}\n\n"
        "Use bash_process_tool(action='wait' or 'output', pid=...) to continue."
    )
    if stdout_text or stderr_text:
        hint += "\n\nPartial output:\n"
        if note:
            hint += f"{note}\n"
        if stdout_text:
            hint += stdout_text
        if stderr_text:
            hint += f"\n[stderr]\n{stderr_text}"
    # A prompt has no newline, so it is in no output line: this is the first place the model can read the question.
    partial_line = reg.get_partial_line(info.pid)
    if partial_line:
        hint += f"\n\nUnfinished last line (no newline yet): {partial_line}"

    return {
        "content": hint,
        "metadata": {
            "auto_yielded": True,
            "background": True,
            "pid": info.pid,
            "status": info.status,
        },
    }


__all__ = [
    "DEFAULT_YIELD_AFTER_SECONDS",
    "build_auto_yield_return",
    "resolve_yield_seconds",
    "should_auto_yield",
    "wait_for_yield_window",
]
