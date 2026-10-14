"""LangGraph checkpointer API assumptions the chat lifecycle relies on.

The disposal steps themselves are covered in ``test_chat_disposal.py``; this module pins the checkpointer
behaviour they depend on (``adelete_thread`` exists, is idempotent and really removes a thread) and that the
other deletion call sites use that same API.
"""

from __future__ import annotations

import pytest

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


# ── Other call sites ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_finalize_uses_adelete_thread() -> None:
    """Verify stream_finalize.py uses adelete_thread (not the defunct adelete)."""
    import inspect

    import app.services.agent.stream_session.stream_finalize as sf

    source = inspect.getsource(sf)
    assert "adelete_thread" in source
    assert 'getattr(checkpointer, "adelete"' not in source, "stream_finalize.py must not use the defunct adelete API"


@pytest.mark.asyncio
async def test_fork_manager_uses_adelete_thread() -> None:
    """Verify conversation_fork_manager.py uses adelete_thread for rollback cleanup."""
    import inspect

    import app.services.chat.conversation_fork_manager as cfm

    source = inspect.getsource(cfm)
    assert "adelete_thread" in source
    assert "lacks delete-single-checkpoint API" not in source, "Outdated comment about missing API should be removed"
