"""Read-only facade over harness BackgroundProcessRegistry for GUI activity panel.

[INPUT]
- myrm_agent_harness.agent.meta_tools.bash._background_registry::get_background_registry

[OUTPUT]
- list_shell_background_tasks: Map in-process shell jobs to API DTOs
- cancel_shell_background_task: Kill a shell job by pid

[POS]
Server business layer. Exposes harness registry to REST without duplicating
process lifecycle logic. Ephemeral (no DB); Kanban agent tasks stay separate.
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel

ShellTaskStatus = Literal["running", "completed", "failed", "cancelled"]


class ShellBackgroundTaskDTO(BaseModel):
    """Shell job row for merged /background-tasks API."""

    kind: Literal["shell"] = "shell"
    task_id: str
    pid: int
    chat_id: str | None = None
    prompt: str
    status: ShellTaskStatus
    created_at: float
    completed_at: float | None = None
    result_preview: str | None = None
    progress_percent: int | None = None


def _map_shell_status(raw: str, exit_code: int | None) -> ShellTaskStatus:
    if raw == "running":
        return "running"
    if raw == "killed":
        return "cancelled"
    if raw == "exited":
        if exit_code is not None and exit_code != 0:
            return "failed"
        return "completed"
    return "failed"


def _command_preview(command: str, *, max_len: int = 120) -> str:
    stripped = command.strip()
    if len(stripped) <= max_len:
        return stripped
    return stripped[: max_len - 3] + "..."


def _progress_from_info(last_progress: dict[str, object] | None) -> int | None:
    if last_progress is None:
        return None
    raw = last_progress.get("progress")
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def list_shell_background_tasks() -> list[ShellBackgroundTaskDTO]:
    """Return all tracked shell jobs (running and recently exited)."""
    from myrm_agent_harness.agent.meta_tools.bash._background_registry import (
        get_background_registry,
    )

    registry = get_background_registry()
    rows: list[ShellBackgroundTaskDTO] = []
    for info in registry.list_processes():
        status = _map_shell_status(info.status, info.exit_code)
        completed_at: float | None = None
        if status != "running":
            completed_at = time.time()

        tail = info.last_stdout_tail or info.last_stderr_tail
        preview = tail[-1] if tail else None

        rows.append(
            ShellBackgroundTaskDTO(
                task_id=f"shell:{info.pid}",
                pid=info.pid,
                chat_id=info.session_id,
                prompt=_command_preview(info.command),
                status=status,
                created_at=info.started_at,
                completed_at=completed_at,
                result_preview=preview,
                progress_percent=_progress_from_info(info.last_progress),
            )
        )
    rows.sort(key=lambda row: row.created_at, reverse=True)
    return rows


async def cancel_shell_background_task(pid: int) -> bool:
    """Kill a shell background job; returns False when pid is unknown."""
    from myrm_agent_harness.agent.meta_tools.bash._background_registry import (
        get_background_registry,
    )

    registry = get_background_registry()
    return await registry.kill(pid, force=False)
