"""Tests for SnapshotInterceptor — harness-factory-delegated snapshot orchestration.

Covers: per-turn dedup, timeout safety, SSE event emission, workspace lock
concurrency, session_id guard, error containment, factory delegation,
trigger mapping, and context None handling.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.checkpoint.snapshot_service import SnapshotInterceptor, _workspace_locks


@pytest.fixture(autouse=True)
def _clear_workspace_locks():
    """Reset module-level locks between tests."""
    _workspace_locks.clear()
    yield
    _workspace_locks.clear()


@pytest.fixture
def interceptor() -> SnapshotInterceptor:
    return SnapshotInterceptor()


def _make_payload(session_id: str = "sess-1") -> dict:
    return {"session_id": session_id, "command": "rm -rf /tmp/test"}


# ---------------------------------------------------------------------------
# 1. Factory delegation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_store_calls_factory(interceptor: SnapshotInterceptor):
    """_get_store lazily initializes via create_file_snapshot_store()."""
    assert interceptor._store is None

    mock_store = AsyncMock()
    with patch(
        "app.services.checkpoint.snapshot_service.create_file_snapshot_store",
        new_callable=AsyncMock,
        return_value=mock_store,
    ):
        store = await interceptor._get_store()

    assert store is mock_store
    assert interceptor._store is mock_store


@pytest.mark.asyncio
async def test_get_store_caches_result(interceptor: SnapshotInterceptor):
    """Second call to _get_store returns cached instance."""
    mock_store = AsyncMock()
    with patch(
        "app.services.checkpoint.snapshot_service.create_file_snapshot_store",
        new_callable=AsyncMock,
        return_value=mock_store,
    ) as mock_factory:
        await interceptor._get_store()
        await interceptor._get_store()

    mock_factory.assert_awaited_once()


# ---------------------------------------------------------------------------
# 2. Per-turn dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_per_turn_dedup_skips_second_call(interceptor: SnapshotInterceptor):
    """Same (workspace, turn) pair should only snapshot once."""
    mock_store = AsyncMock()
    mock_store.take_snapshot = AsyncMock(return_value="abc123")
    interceptor._store = mock_store

    with patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock):
        cache_key = ("/tmp/ws", "turn-1")
        meta: dict[str, object] = {"agent_id": "a"}
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", cache_key, meta)
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", cache_key, meta)

    assert mock_store.take_snapshot.await_count == 1


@pytest.mark.asyncio
async def test_different_turns_both_snapshot(interceptor: SnapshotInterceptor):
    """Different turn IDs should each get their own snapshot."""
    mock_store = AsyncMock()
    mock_store.take_snapshot = AsyncMock(return_value="abc123")
    interceptor._store = mock_store

    meta: dict[str, object] = {"agent_id": "a"}
    with patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock):
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", ("/tmp/ws", "turn-1"), meta)
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-2", ("/tmp/ws", "turn-2"), meta)

    assert mock_store.take_snapshot.await_count == 2


# ---------------------------------------------------------------------------
# 3. session_id guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_skips_when_no_session_id(interceptor: SnapshotInterceptor):
    """Payload without session_id => early return, no snapshot."""
    with patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock:
        await interceptor.before_destructive_action("/tmp/ws", "bash", {"command": "ls"})

    mock.assert_not_awaited()


# ---------------------------------------------------------------------------
# 4. Event emission uses correct API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_snapshot_event_uses_event_bus(interceptor: SnapshotInterceptor):
    """_emit_snapshot_event should call get_event_bus().publish(AppEvent(...))."""
    mock_bus = MagicMock()

    mock_module = MagicMock()
    mock_module.get_event_bus.return_value = mock_bus
    mock_module.AppEventType.SYSTEM_NOTIFICATION = "system_notification"

    with patch.dict("sys.modules", {"app.services.event.app_event_bus": mock_module}):
        await interceptor._emit_snapshot_event("chat-123", "bash", "agent-1")

    mock_bus.publish.assert_called_once()
    mock_module.AppEvent.assert_called_once()
    call_kwargs = mock_module.AppEvent.call_args.kwargs
    assert call_kwargs["event_type"] == "system_notification"
    assert call_kwargs["data"]["meta_data"]["type"] == "snapshot_created"
    assert call_kwargs["data"]["meta_data"]["chat_id"] == "chat-123"
    assert call_kwargs["data"]["meta_data"]["action"] == "bash"


# ---------------------------------------------------------------------------
# 5. Snapshot error does not propagate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_error_caught_gracefully(interceptor: SnapshotInterceptor):
    """Errors in snapshot creation should be caught, not propagated."""
    mock_store = AsyncMock()
    mock_store.take_snapshot = AsyncMock(side_effect=RuntimeError("git failed"))
    interceptor._store = mock_store

    meta: dict[str, object] = {"agent_id": "a"}
    with patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock):
        await interceptor._safe_snapshot_with_lock("/tmp/ws", "bash", "c", "a", "turn-1", ("/tmp/ws", "turn-1"), meta)

    assert not interceptor._snapshotted_turns.get(("/tmp/ws", "turn-1"))


# ---------------------------------------------------------------------------
# 6. Trigger mapping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_mapping(interceptor: SnapshotInterceptor):
    """Each action_type should map to the correct SnapshotTrigger."""
    from myrm_agent_harness.agent.file_snapshot.types import SnapshotTrigger

    mock_store = AsyncMock()
    mock_store.take_snapshot = AsyncMock(return_value="abc123")
    interceptor._store = mock_store

    test_cases = [
        ("bash", SnapshotTrigger.EXECUTE_TERMINAL),
        ("file_write", SnapshotTrigger.WRITE_FILE),
        ("file_append", SnapshotTrigger.WRITE_FILE),
        ("file_delete", SnapshotTrigger.DELETE_FILE),
        ("patch_file", SnapshotTrigger.PATCH_FILE),
        ("unknown_action", SnapshotTrigger.MANUAL),
    ]

    for action_type, expected_trigger in test_cases:
        interceptor._snapshotted_turns.clear()
        mock_store.take_snapshot.reset_mock()

        meta: dict[str, object] = {"agent_id": "a"}
        with patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock):
            await interceptor._safe_snapshot_with_lock(
                "/tmp/ws", action_type, "c", "a", f"turn-{action_type}", ("/tmp/ws", f"turn-{action_type}"), meta
            )

        call_kwargs = mock_store.take_snapshot.call_args.kwargs
        assert call_kwargs["trigger"] == expected_trigger, f"Failed for action_type={action_type}"


# ---------------------------------------------------------------------------
# 7. Workspace lock isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_workspace_locks_are_per_workspace():
    """Different workspaces should have independent locks."""
    lock_a = _workspace_locks["/ws/a"]
    lock_b = _workspace_locks["/ws/b"]
    assert lock_a is not lock_b

    lock_a2 = _workspace_locks["/ws/a"]
    assert lock_a is lock_a2


# ---------------------------------------------------------------------------
# 8. Timeout behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_does_not_block_caller(interceptor: SnapshotInterceptor):
    """If snapshot takes > 3s, before_destructive_action returns without waiting."""

    async def _slow_snapshot(*args, **kwargs):
        await asyncio.sleep(10)

    mock_context = MagicMock(
        get_current_turn_id=MagicMock(return_value="turn-1"),
        get_current_chat_id=MagicMock(return_value="chat-1"),
        get_current_agent_id=MagicMock(return_value="agent-1"),
    )

    with patch.object(interceptor, "_safe_snapshot_with_lock", side_effect=_slow_snapshot):
        with patch.dict("sys.modules", {"app.ai_agents.general_agent.context": mock_context}):
            await asyncio.wait_for(
                interceptor.before_destructive_action("/tmp/ws", "bash", _make_payload()),
                timeout=5.0,
            )


# ---------------------------------------------------------------------------
# 9. before_destructive_action with context returning None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_before_destructive_action_handles_none_context(interceptor: SnapshotInterceptor):
    """When context functions return None, defaults to 'unknown_*' and still works."""
    mock_context = MagicMock(
        get_current_turn_id=MagicMock(return_value=None),
        get_current_chat_id=MagicMock(return_value=None),
        get_current_agent_id=MagicMock(return_value=None),
    )

    with (
        patch.dict("sys.modules", {"app.ai_agents.general_agent.context": mock_context}),
        patch.object(interceptor, "_safe_snapshot_with_lock", new_callable=AsyncMock) as mock_snapshot,
    ):
        await interceptor.before_destructive_action("/tmp/ws", "bash", _make_payload())

    mock_snapshot.assert_awaited_once()
    call_args = mock_snapshot.call_args
    assert call_args.args[2] == "unknown_chat"
    assert call_args.args[3] == "unknown_agent"
    assert call_args.args[4] == "unknown_turn"


# ---------------------------------------------------------------------------
# 10. _emit_snapshot_event silently catches exceptions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_snapshot_event_catches_exceptions(interceptor: SnapshotInterceptor):
    """_emit_snapshot_event should not raise even if event bus fails."""
    mock_module = MagicMock()
    mock_module.get_event_bus.side_effect = RuntimeError("bus broken")

    with patch.dict("sys.modules", {"app.services.event.app_event_bus": mock_module}):
        await interceptor._emit_snapshot_event("chat-1", "bash", "agent-1")


# ---------------------------------------------------------------------------
# 11. Concurrent snapshots on different workspaces
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_snapshots_different_workspaces(interceptor: SnapshotInterceptor):
    """Two different workspaces can snapshot concurrently without blocking."""
    mock_store = AsyncMock()
    call_order: list[str] = []

    async def _mock_take_snapshot(working_dir: str = "", **kwargs):
        call_order.append(f"start-{working_dir}")
        await asyncio.sleep(0.05)
        call_order.append(f"end-{working_dir}")
        return "abc123"

    mock_store.take_snapshot = _mock_take_snapshot
    interceptor._store = mock_store

    meta: dict[str, object] = {"agent_id": "a"}
    with patch.object(interceptor, "_emit_snapshot_event", new_callable=AsyncMock):
        await asyncio.gather(
            interceptor._safe_snapshot_with_lock("/ws/a", "bash", "c", "a", "t1", ("/ws/a", "t1"), meta),
            interceptor._safe_snapshot_with_lock("/ws/b", "bash", "c", "a", "t1", ("/ws/b", "t1"), meta),
        )

    assert len(call_order) == 4
    assert "start-/ws/a" in call_order
    assert "start-/ws/b" in call_order
