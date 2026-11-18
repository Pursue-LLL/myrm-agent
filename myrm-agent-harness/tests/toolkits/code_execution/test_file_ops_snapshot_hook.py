"""Tests for LocalFileOpsMixin destructive-action hook payloads.

Every mutation (the four write variants and delete) reports its target to the execution interceptor before it
happens, carrying the current chat session id so the server-side SnapshotInterceptor can create workspace
snapshots for file operations (not only bash). Without a bound chat context the session_id is None and the hook
stays inert. A mutation a protection rule refuses is neither reported nor performed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.context_management.infra.session_lock import (
    reset_current_chat_id,
    set_current_chat_id,
)
from myrm_agent_harness.toolkits.code_execution.executors.local._file_ops import (
    LocalFileOpsMixin,
)

# Every mutation of the mixin: its arguments and the action type it reports.
_MUTATIONS: dict[str, tuple[tuple[object, ...], str]] = {
    "write_file": (("a.txt", "text"), "file_write"),
    "write_file_bytes": (("a.txt", b"bytes"), "file_write"),
    "write_file_atomic": (("a.txt", "text"), "file_write"),
    "write_file_bytes_atomic": (("a.txt", b"bytes"), "file_write"),
    "delete_file": (("a.txt",), "file_delete"),
}


class _TestOps(LocalFileOpsMixin):
    """Concrete mixin host backed by a temp workspace."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._current_workspace: Path | None = None

    async def resolve_path(self, path: str) -> str:
        return str(self._root / path)

    def _log_context_file_access(self, path: str, success: bool) -> None:
        pass

    @property
    def workspace_path(self) -> str:
        return str(self._root)


class _RefusingOps(_TestOps):
    """A host whose write guard refuses every path."""

    def _guard_write(self, resolved_path: str) -> None:
        raise PermissionError(f"Write denied: '{resolved_path}'")


def _hook_patch():
    return patch(
        "myrm_agent_harness.toolkits.code_execution.executors.local._file_ops.trigger_destructive_action_hook",
        new_callable=AsyncMock,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", _MUTATIONS)
async def test_every_mutation_reports_its_target_before_it_happens(tmp_path: Path, operation: str) -> None:
    args, action_type = _MUTATIONS[operation]
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")
    on_disk_at_report: list[bytes] = []
    token = set_current_chat_id("chat-abc")
    try:
        with _hook_patch() as hook:
            hook.side_effect = lambda **_: on_disk_at_report.append(target.read_bytes())
            await getattr(_TestOps(tmp_path), operation)(*args)
    finally:
        reset_current_chat_id(token)

    hook.assert_awaited_once()
    kwargs = hook.call_args.kwargs
    assert kwargs["workspace_path"] == str(tmp_path)
    assert kwargs["action_type"] == action_type
    assert kwargs["payload"] == {"path": str(target), "session_id": "chat-abc"}
    assert on_disk_at_report == [b"old"]
    assert target.exists() == (action_type == "file_write")
    if target.exists():
        assert target.read_bytes() != b"old"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", _MUTATIONS)
async def test_outside_an_agent_turn_the_report_carries_no_session(tmp_path: Path, operation: str) -> None:
    """Outside an agent turn no chat id is bound and the hook stays inert."""
    args, _ = _MUTATIONS[operation]
    (tmp_path / "a.txt").write_bytes(b"old")
    with _hook_patch() as hook:
        await getattr(_TestOps(tmp_path), operation)(*args)

    assert hook.call_args.kwargs["payload"]["session_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", _MUTATIONS)
async def test_a_refused_mutation_is_neither_reported_nor_performed(tmp_path: Path, operation: str) -> None:
    args, _ = _MUTATIONS[operation]
    target = tmp_path / "a.txt"
    target.write_bytes(b"old")
    with _hook_patch() as hook, pytest.raises(PermissionError):
        await getattr(_RefusingOps(tmp_path), operation)(*args)

    hook.assert_not_awaited()
    assert target.read_bytes() == b"old"
