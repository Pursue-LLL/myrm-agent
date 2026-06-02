"""Unit tests for LangGraph checkpointer cleanup across all chat lifecycle paths.

Validates that ``_cleanup_checkpointer`` correctly calls ``adelete_thread``
for both ``chat_id`` and ``chat_{chat_id}`` thread variants, handles errors
gracefully, and is wired into every session termination path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.chat.chat_crud import _ChatCrudMixin


@pytest.fixture
def mock_checkpointer() -> MagicMock:
    cp = MagicMock()
    cp.adelete_thread = AsyncMock()
    return cp


# ── Core _cleanup_checkpointer Tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_cleanup_calls_adelete_thread_for_both_ids(mock_checkpointer: MagicMock) -> None:
    """Should call adelete_thread for both chat_id and chat_{chat_id}."""
    with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
        await _ChatCrudMixin._cleanup_checkpointer("abc-123")

    assert mock_checkpointer.adelete_thread.call_count == 2
    mock_checkpointer.adelete_thread.assert_any_call("abc-123")
    mock_checkpointer.adelete_thread.assert_any_call("chat_abc-123")


@pytest.mark.asyncio
async def test_cleanup_handles_adelete_exception_gracefully(mock_checkpointer: MagicMock) -> None:
    """adelete_thread failure should be caught, not propagated."""
    mock_checkpointer.adelete_thread = AsyncMock(side_effect=RuntimeError("DB locked"))
    with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
        await _ChatCrudMixin._cleanup_checkpointer("err-chat")  # must not raise


@pytest.mark.asyncio
async def test_cleanup_handles_get_checkpointer_failure() -> None:
    """If get_checkpointer itself raises, cleanup should not propagate."""
    with patch("app.platform_utils.get_checkpointer", side_effect=RuntimeError("not initialized")):
        await _ChatCrudMixin._cleanup_checkpointer("no-cp")  # must not raise


@pytest.mark.asyncio
async def test_cleanup_idempotent(mock_checkpointer: MagicMock) -> None:
    """Calling cleanup multiple times for same chat_id should be safe."""
    with patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer):
        await _ChatCrudMixin._cleanup_checkpointer("idem-1")
        await _ChatCrudMixin._cleanup_checkpointer("idem-1")

    assert mock_checkpointer.adelete_thread.call_count == 4  # 2 calls * 2 invocations


# ── Integration: MemorySaver round-trip ──────────────────────────────


@pytest.mark.asyncio
async def test_memorysaver_adelete_thread_api_exists() -> None:
    """Verify adelete_thread exists on real MemorySaver and is idempotent."""
    from langgraph.checkpoint.memory import MemorySaver

    ms = MemorySaver()
    assert hasattr(ms, "adelete_thread")
    assert callable(ms.adelete_thread)
    await ms.adelete_thread("nonexistent")  # must not raise


@pytest.mark.asyncio
async def test_memorysaver_full_cycle() -> None:
    """Add checkpoint → delete thread → verify data is gone."""
    from langgraph.checkpoint.memory import MemorySaver

    ms = MemorySaver()
    config = {
        "configurable": {
            "thread_id": "cycle-test",
            "checkpoint_ns": "",
            "checkpoint_id": "cp-1",
        }
    }
    cp_data = {
        "v": 1,
        "id": "cp-1",
        "ts": "2026-01-01T00:00:00+00:00",
        "channel_values": {},
        "channel_versions": {},
        "versions_seen": {},
        "pending_sends": [],
    }
    ms.put(config, cp_data, {}, {})
    items_before = list(ms.list({"configurable": {"thread_id": "cycle-test"}}))
    assert len(items_before) == 1

    await ms.adelete_thread("cycle-test")
    items_after = list(ms.list({"configurable": {"thread_id": "cycle-test"}}))
    assert len(items_after) == 0


# ── Wiring verification: all call sites ─────────────────────────────


@pytest.mark.asyncio
async def test_permanently_delete_calls_cleanup(mock_checkpointer: MagicMock) -> None:
    """permanently_delete_chat should call _cleanup_checkpointer on success."""
    with (
        patch("app.platform_utils.get_checkpointer", return_value=mock_checkpointer),
        patch.object(_ChatCrudMixin, "permanently_delete_chat", wraps=_ChatCrudMixin.permanently_delete_chat),
    ):
        import app.services.chat.chat_crud as mod
        assert "_cleanup_checkpointer" in dir(mod._ChatCrudMixin)


@pytest.mark.asyncio
async def test_scheduler_auto_purge_includes_cleanup() -> None:
    """Verify schedulers.py references _cleanup_checkpointer for auto-purge."""
    import inspect

    import app.lifecycle.schedulers as sched

    source = inspect.getsource(sched)
    assert "_cleanup_checkpointer" in source, (
        "schedulers.py auto-purge must call _cleanup_checkpointer"
    )


@pytest.mark.asyncio
async def test_stream_finalize_uses_adelete_thread() -> None:
    """Verify stream_finalize.py uses adelete_thread (not the defunct adelete)."""
    import inspect

    import app.services.agent.stream_session.stream_finalize as sf

    source = inspect.getsource(sf)
    assert "adelete_thread" in source
    assert 'getattr(checkpointer, "adelete"' not in source, (
        "stream_finalize.py must not use the defunct adelete API"
    )


@pytest.mark.asyncio
async def test_fork_manager_uses_adelete_thread() -> None:
    """Verify conversation_fork_manager.py uses adelete_thread for rollback cleanup."""
    import inspect

    import app.services.chat.conversation_fork_manager as cfm

    source = inspect.getsource(cfm)
    assert "adelete_thread" in source
    assert "lacks delete-single-checkpoint API" not in source, (
        "Outdated comment about missing API should be removed"
    )
