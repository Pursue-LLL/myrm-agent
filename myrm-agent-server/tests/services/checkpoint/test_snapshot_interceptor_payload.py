"""Tests for how SnapshotInterceptor reads the destructive-action payload.

Covers: external effects reported by the harness (recorded on the task airbag independently of the
per-turn snapshot dedup) and the privacy ladder's check of the target path the payload names.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.api import PrivacyFailClosedViolationError
from myrm_agent_harness.toolkits.code_execution.interceptor import DestructiveActionPayload

from app.services.checkpoint.snapshot_service import SnapshotInterceptor

# ---------------------------------------------------------------------------
# 1. External effects reported by the harness
# ---------------------------------------------------------------------------


def _effect_payload(*, destructive: bool, effects: list[str], session_id: str = "sess-1") -> DestructiveActionPayload:
    return {"session_id": session_id, "command": "cmd", "destructive": destructive, "external_effects": effects}


@pytest.mark.asyncio
async def test_effect_only_command_is_recorded_without_a_snapshot(interceptor: SnapshotInterceptor) -> None:
    """A command that only reaches outside the workspace has nothing for a file snapshot to capture."""
    airbag = MagicMock()
    with (
        patch("app.services.checkpoint.snapshot_service.get_task_airbag_service", return_value=airbag),
        patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock_snapshot,
    ):
        await interceptor.before_destructive_action(
            "/tmp/ws", "bash", _effect_payload(destructive=False, effects=["container_cloud"])
        )

    airbag.record_session_external_effects.assert_called_once_with("sess-1", ["container_cloud"])
    mock_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_destructive_command_with_effects_snapshots_and_records(interceptor: SnapshotInterceptor) -> None:
    airbag = MagicMock()
    with (
        patch("app.services.checkpoint.snapshot_service.get_task_airbag_service", return_value=airbag),
        patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock_snapshot,
    ):
        await interceptor.before_destructive_action("/tmp/ws", "bash", _effect_payload(destructive=True, effects=["publish"]))

    airbag.record_session_external_effects.assert_called_once_with("sess-1", ["publish"])
    mock_snapshot.assert_awaited_once()
    assert mock_snapshot.call_args.args[-1]["external_effects"] == ["publish"]


@pytest.mark.asyncio
async def test_effects_are_recorded_after_the_turn_was_already_snapshotted(interceptor: SnapshotInterceptor) -> None:
    """Per-turn dedup guards snapshots only; a later external effect in the same turn must still be recorded."""
    airbag = MagicMock()
    with (
        patch("app.services.checkpoint.snapshot_service.get_task_airbag_service", return_value=airbag),
        patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock),
    ):
        interceptor._mark_turn_snapshotted(("/tmp/ws", "unknown_turn"))
        await interceptor.before_destructive_action("/tmp/ws", "bash", _effect_payload(destructive=True, effects=["database"]))

    airbag.record_session_external_effects.assert_called_once_with("sess-1", ["database"])


@pytest.mark.asyncio
async def test_payload_without_effects_never_touches_the_airbag(interceptor: SnapshotInterceptor) -> None:
    payload: DestructiveActionPayload = {"session_id": "sess-1", "command": "rm -rf /tmp/test"}
    airbag = MagicMock()
    with (
        patch("app.services.checkpoint.snapshot_service.get_task_airbag_service", return_value=airbag),
        patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock_snapshot,
    ):
        await interceptor.before_destructive_action("/tmp/ws", "bash", payload)

    airbag.record_session_external_effects.assert_not_called()
    mock_snapshot.assert_awaited_once()
    assert "external_effects" not in mock_snapshot.call_args.args[-1]


# ---------------------------------------------------------------------------
# 2. Privacy ladder checks the target the payload names
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_target_outside_the_workspace_is_not_snapshotted(interceptor: SnapshotInterceptor) -> None:
    payload: DestructiveActionPayload = {"session_id": "sess-1", "path": "/elsewhere/file.txt"}
    with patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock_snapshot:
        with pytest.raises(PrivacyFailClosedViolationError):
            await interceptor.before_destructive_action("/tmp/ws", "file_write", payload)

    mock_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_target_inside_the_workspace_is_snapshotted(interceptor: SnapshotInterceptor) -> None:
    payload: DestructiveActionPayload = {"session_id": "sess-1", "path": "/tmp/ws/src/file.txt"}
    with patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock_snapshot:
        await interceptor.before_destructive_action("/tmp/ws", "file_write", payload)

    mock_snapshot.assert_awaited_once()
