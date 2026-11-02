"""Shell job rows built from the durable ledger, and the bounded prompt read for a job waiting for input."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.bash._background.job_store_core import (
    BackgroundJobRecord,
    BackgroundJobStoreStatus,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import BackgroundProcessInfo

from app.services.agent.shell_background_tasks import (
    ShellBackgroundTaskDTO,
    _coerce_interactive_prompt,
    _map_shell_status,
    list_shell_background_tasks,
)

_HOOKS = "myrm_agent_harness.api.hooks"
_CHOICE_LINES = ["Select the deployment target:", "1) staging", "2) production", "Enter choice:"]


def _record(
    job_id: str, *, status: BackgroundJobStoreStatus = "running", vault_log_ref: str | None = None
) -> BackgroundJobRecord:
    return BackgroundJobRecord(
        job_id=job_id,
        pid=4242,
        session_id="chat-ledger",
        command="npm run serve",
        status=status,
        started_at=5.0,
        completed_at=None,
        exit_code=None,
        error_category=None,
        finish_processed=False,
        vault_log_ref=vault_log_ref,
    )


def _running_job(job_id: str, pid: int) -> BackgroundProcessInfo:
    return BackgroundProcessInfo(job_id=job_id, pid=pid, command="make", session_id="chat", started_at=1.0, status="running")


def _waiting_job(job_id: str = "job-waiting", pid: int = 101) -> BackgroundProcessInfo:
    return BackgroundProcessInfo(
        job_id=job_id,
        pid=pid,
        command="npm create vite",
        session_id="chat-prompt",
        started_at=1.0,
        status="running",
        waiting_for_input=True,
    )


def _rows(registry: object, store: object | None = None) -> list[ShellBackgroundTaskDTO]:
    with (
        patch(f"{_HOOKS}.get_background_registry", return_value=registry),
        patch(f"{_HOOKS}.get_background_job_store", return_value=store),
    ):
        return list_shell_background_tasks()


def _registry_listing(info: BackgroundProcessInfo, get_output: Callable[..., object]) -> MagicMock:
    registry = MagicMock()
    registry.list_processes.return_value = [info]
    registry.get_output.side_effect = get_output
    return registry


@pytest.mark.parametrize(
    ("raw", "exit_code", "expected"),
    [
        ("running", None, "running"),
        ("orphaned", None, "orphaned"),
        ("killed", None, "cancelled"),
        ("exited", 0, "completed"),
        ("exited", None, "completed"),
        ("exited", 2, "failed"),
        ("unknown", None, "failed"),
    ],
)
def test_a_registry_status_maps_to_the_panel_status(raw: str, exit_code: int | None, expected: str) -> None:
    assert _map_shell_status(raw, exit_code) == expected


def test_a_job_only_the_ledger_knows_is_listed_as_orphaned_after_a_restart() -> None:
    registry = MagicMock()
    registry.list_processes.return_value = []
    store = MagicMock()
    store.list_recent.return_value = [_record("job-ledger", status="orphaned", vault_log_ref="vault://log")]

    rows = _rows(registry, store)

    assert [(row.task_id, row.status, row.pid, row.vault_log_ref) for row in rows] == [
        ("shell:job-ledger", "orphaned", 4242, "vault://log")
    ]
    assert rows[0].leftover_processes == 0


def test_a_live_job_takes_its_log_reference_from_the_ledger_when_it_has_none() -> None:
    info = _running_job("job-live", 7)
    registry = MagicMock()
    registry.list_processes.return_value = [info]
    store = MagicMock()
    store.get_by_job_id.return_value = None
    store.list_recent.return_value = [_record("job-live", vault_log_ref="vault://from-ledger")]

    rows = _rows(registry, store)

    assert len(rows) == 1
    assert rows[0].vault_log_ref == "vault://from-ledger"


def test_a_live_job_reads_its_log_reference_straight_from_the_ledger() -> None:
    info = _running_job("job-direct", 8)
    registry = MagicMock()
    registry.list_processes.return_value = [info]
    store = MagicMock()
    store.get_by_job_id.return_value = _record("job-direct", vault_log_ref="vault://direct")
    store.list_recent.return_value = []

    assert _rows(registry, store)[0].vault_log_ref == "vault://direct"


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_a_prompt_is_read_from_either_output_stream(stream: str) -> None:
    other = "stderr" if stream == "stdout" else "stdout"
    registry = _registry_listing(_waiting_job(), lambda pid, *, max_lines: {stream: _CHOICE_LINES, other: []})

    prompt = _rows(registry)[0].interactive_prompt

    assert prompt is not None
    assert [option.label for option in prompt.options][:2] == ["staging", "production"]


@pytest.mark.parametrize(
    "payload",
    ["not a mapping", {"stdout": [], "stderr": []}, {"stdout": [1, 2], "stderr": [None]}, {"stdout": "text"}],
    ids=["not_a_mapping", "no_lines", "no_text_lines", "not_a_list"],
)
def test_no_prompt_is_read_from_output_without_text_lines(payload: object) -> None:
    registry = _registry_listing(_waiting_job(), lambda pid, *, max_lines: payload)

    assert _rows(registry)[0].interactive_prompt is None


def test_a_job_whose_output_cannot_be_read_has_no_prompt() -> None:
    def unreadable(pid: int, *, max_lines: int) -> object:
        raise RuntimeError("output buffer gone")

    registry = _registry_listing(_waiting_job(), unreadable)

    rows = _rows(registry)

    assert rows[0].waiting_for_input is True
    assert rows[0].interactive_prompt is None


def test_a_malformed_prompt_payload_is_dropped() -> None:
    assert _coerce_interactive_prompt("not a mapping") is None
    assert _coerce_interactive_prompt({"kind": "confirm"}) is None
