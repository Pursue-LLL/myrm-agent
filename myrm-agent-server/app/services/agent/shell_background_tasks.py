"""Read-only facade over harness registry + durable job store for GUI activity panel.

[INPUT]
- myrm_agent_harness.api.hooks::get_background_registry
- myrm_agent_harness.api.hooks::get_background_job_store (POS: BSDL Core ledger)

[OUTPUT]
- list_shell_background_tasks: Merge in-process + durable store rows
- cancel_shell_background_task: Kill a shell job by pid

[POS]
Server business layer. Exposes harness registry to REST without duplicating
process lifecycle logic. Durable metadata via BackgroundJobStore on Volume.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.api.hooks import map_store_status_to_shell_task_status
from pydantic import BaseModel

from app.platform_utils.workspace_session import to_rest_chat_id

ShellTaskStatus = Literal["running", "completed", "failed", "cancelled", "orphaned"]


class ShellBackgroundTaskDTO(BaseModel):
    """Shell job row for merged /background-tasks API."""

    kind: Literal["shell"] = "shell"
    task_id: str
    job_id: str
    pid: int | None = None
    chat_id: str | None = None
    prompt: str
    status: ShellTaskStatus
    created_at: float
    completed_at: float | None = None
    result_preview: str | None = None
    progress_percent: int | None = None
    exit_code: int | None = None
    error_category: str | None = None
    vault_log_ref: str | None = None


def _map_shell_status(raw: str, exit_code: int | None) -> ShellTaskStatus:
    if raw == "running":
        return "running"
    if raw == "orphaned":
        return "orphaned"
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


def _redact_preview(text: str | None) -> str | None:
    if not text:
        return None
    from myrm_agent_harness.agent.security.redact import redact_sensitive_text

    return redact_sensitive_text(text)


def _vault_log_ref_from_store(job_id: str) -> str | None:
    from myrm_agent_harness.api.hooks import get_background_job_store

    store = get_background_job_store()
    if store is None:
        return None
    record = store.get_by_job_id(job_id)
    if record is None or not record.vault_log_ref:
        return None
    return record.vault_log_ref


def _row_from_registry_info(info: object) -> ShellBackgroundTaskDTO:
    from myrm_agent_harness.api.hooks import BackgroundProcessInfo

    assert isinstance(info, BackgroundProcessInfo)
    status = _map_shell_status(info.status, info.exit_code)
    completed_at: float | None = None
    if status != "running" and info.last_progress is not None:
        raw_ts = info.last_progress.get("updated_at")
        if isinstance(raw_ts, (int, float)):
            completed_at = float(raw_ts)

    tail = info.last_stdout_tail or info.last_stderr_tail
    preview = _redact_preview(tail[-1] if tail else None)

    return ShellBackgroundTaskDTO(
        task_id=f"shell:{info.job_id}",
        job_id=info.job_id,
        pid=info.pid,
        chat_id=to_rest_chat_id(info.session_id),
        prompt=_command_preview(info.command),
        status=status,
        created_at=info.started_at,
        completed_at=completed_at,
        result_preview=preview,
        progress_percent=_progress_from_info(info.last_progress),
        exit_code=info.exit_code,
        error_category=info.error_category,
        vault_log_ref=info.vault_log_ref or _vault_log_ref_from_store(info.job_id),
    )


def _row_from_store_record(record: object) -> ShellBackgroundTaskDTO:
    from myrm_agent_harness.api.hooks import BackgroundJobRecord

    assert isinstance(record, BackgroundJobRecord)
    status = map_store_status_to_shell_task_status(record.status, record.exit_code)
    return ShellBackgroundTaskDTO(
        task_id=f"shell:{record.job_id}",
        job_id=record.job_id,
        pid=record.pid,
        chat_id=to_rest_chat_id(record.session_id),
        prompt=_command_preview(record.command),
        status=status,
        created_at=record.started_at,
        completed_at=record.completed_at,
        result_preview=None,
        progress_percent=None,
        exit_code=record.exit_code,
        error_category=record.error_category,
        vault_log_ref=record.vault_log_ref,
    )


def list_shell_background_tasks() -> list[ShellBackgroundTaskDTO]:
    """Return tracked shell jobs from live registry merged with durable store."""
    from myrm_agent_harness.api.hooks import (
        get_background_job_store,
        get_background_registry,
    )

    registry = get_background_registry()
    merged: dict[str, ShellBackgroundTaskDTO] = {}

    for info in registry.list_processes():
        row = _row_from_registry_info(info)
        merged[row.job_id] = row

    store = get_background_job_store()
    if store is not None:
        for record in store.list_recent(limit=200):
            if record.job_id in merged:
                live = merged[record.job_id]
                if live.vault_log_ref is None and record.vault_log_ref:
                    merged[record.job_id] = live.model_copy(
                        update={"vault_log_ref": record.vault_log_ref}
                    )
                continue
            merged[record.job_id] = _row_from_store_record(record)

    rows = list(merged.values())
    rows.sort(key=lambda row: row.created_at, reverse=True)
    return rows


def find_shell_background_task(task_suffix: str) -> ShellBackgroundTaskDTO | None:
    """Resolve shell: task id suffix (job_id UUID hex)."""
    for row in list_shell_background_tasks():
        if row.job_id == task_suffix:
            return row
    return None


async def cancel_shell_background_task(pid: int) -> bool:
    """Kill a shell background job; returns False when pid is unknown."""
    from myrm_agent_harness.api.hooks import get_background_registry

    registry = get_background_registry()
    return await registry.kill(pid, force=False)


async def write_shell_background_stdin(
    pid: int,
    data: str,
    *,
    submit: bool = False,
    close: bool = False,
) -> dict[str, object]:
    """Write to a running shell background job stdin; returns harness status dict."""
    from myrm_agent_harness.api.hooks import get_background_registry

    registry = get_background_registry()
    return await registry.write_stdin(
        pid,
        data,
        append_newline=submit,
        close=close,
    )


def shell_registry_is_ephemeral() -> bool:
    """False when durable BackgroundJobStore is configured on Volume."""
    from myrm_agent_harness.api.hooks import get_background_job_store

    return get_background_job_store() is None
