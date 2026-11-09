import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.agent.background_worker import idle_tasks
from myrm_agent_harness.agent.background_worker.idle_tasks import (
    _idle_task_handlers,
    _run_context_compaction,
    default_idle_callback,
    register_context_compaction_handler,
    register_idle_task_handler,
)
from myrm_agent_harness.agent.background_worker.idle_worker import _idle_tasks, cancel_idle_task, schedule_idle_task
from myrm_agent_harness.agent.background_worker.registry import IdleTaskRecord, IdleTaskRegistry
from myrm_agent_harness.runtime.maintenance.protocols import CapacityDenial, CapacityTicket
from tests.support.idle_task_runner import idle_record, run_task_collecting_events


@pytest.fixture(autouse=True)
def reset_context_compaction_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(idle_tasks, "_context_compaction_handler", None)


@pytest.fixture(autouse=True)
def clean_idle_tasks():
    # Clean up any scheduled tasks before and after each test
    _idle_tasks.clear()
    yield
    for task in _idle_tasks.values():
        if not task.done():
            task.cancel()
    _idle_tasks.clear()


@pytest.mark.asyncio
async def test_schedule_and_cancel_idle_task():
    session_id = "test_session_1"
    callback_executed = False

    async def mock_callback():
        nonlocal callback_executed
        callback_executed = True

    # Schedule task
    schedule_idle_task(session_id, mock_callback, delay_seconds=10)
    task = _idle_tasks[session_id]
    assert session_id in _idle_tasks

    # Cancel task
    cancel_idle_task(session_id)
    await asyncio.sleep(0.01)  # allow task state to update
    assert task.cancelled() or task.done()
    assert session_id not in _idle_tasks

    # Ensure callback was not executed
    assert not callback_executed


@pytest.mark.asyncio
async def test_schedule_idle_task_execution():
    session_id = "test_session_2"
    callback_executed = False

    async def mock_callback():
        nonlocal callback_executed
        callback_executed = True

    # Schedule task with very short delay
    schedule_idle_task(session_id, mock_callback, delay_seconds=0)

    # Yield control to allow background task to run
    await asyncio.sleep(0.1)

    assert callback_executed
    assert session_id not in _idle_tasks


@pytest.mark.asyncio
@patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_maintenance_scheduler")
async def test_default_idle_callback_denied(mock_get_scheduler):
    # Setup scheduler mock to deny capacity
    mock_scheduler = AsyncMock()
    mock_denial = CapacityDenial(reason="System overloaded")
    mock_scheduler.request_capacity.return_value = mock_denial
    mock_get_scheduler.return_value = mock_scheduler

    # Setup EventBus mock (should not be called for denied capacity)
    mock_event_bus = MagicMock()

    # Setup registry mock
    mock_registry = AsyncMock(spec=IdleTaskRegistry)
    mock_registry.acquire_next.return_value = IdleTaskRecord(
        id=1,
        session_id="sess1",
        task_type="cognitive_consolidation",
        payload={},
        status="running",
        created_at=0.0,
    )

    with patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_event_bus", return_value=mock_event_bus):
        ran = await default_idle_callback("test_session_4", mock_registry)

    assert ran is False
    mock_scheduler.request_capacity.assert_called_once()
    mock_event_bus.publish.assert_not_called()
    mock_registry.requeue.assert_awaited_once_with(1)


@pytest.mark.asyncio
@patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_maintenance_scheduler")
async def test_default_idle_callback_no_scheduler(mock_get_scheduler):
    # Setup scheduler mock to return None
    mock_get_scheduler.return_value = None

    # Setup registry mock
    mock_registry = AsyncMock(spec=IdleTaskRegistry)
    mock_registry.acquire_next.return_value = IdleTaskRecord(
        id=1,
        session_id="sess1",
        task_type="cognitive_consolidation",
        payload={},
        status="running",
        created_at=0.0,
    )

    ran = await default_idle_callback("test_session_5", mock_registry)

    # Without a scheduler nothing may run, and the task stays available for a later window
    assert ran is False
    mock_registry.requeue.assert_awaited_once_with(1)
    mock_registry.mark_error.assert_not_called()


# ---------------------------------------------------------------------------
# context_compaction handler tests
# ---------------------------------------------------------------------------


class TestRegisterIdleTaskHandler:
    """Tests for the handler registration mechanism."""

    def test_register_and_retrieve(self) -> None:
        handler = AsyncMock()
        register_idle_task_handler("_test_handler", handler)
        assert _idle_task_handlers["_test_handler"] is handler
        del _idle_task_handlers["_test_handler"]

    def test_overwrite_handler(self) -> None:
        h1 = AsyncMock()
        h2 = AsyncMock()
        register_idle_task_handler("_test_overwrite", h1)
        register_idle_task_handler("_test_overwrite", h2)
        assert _idle_task_handlers["_test_overwrite"] is h2
        del _idle_task_handlers["_test_overwrite"]


@pytest.mark.asyncio
class TestRunContextCompaction:
    """Tests for the _run_context_compaction function."""

    async def test_skip_when_no_chat_id(self) -> None:
        event_bus = MagicMock()
        task = IdleTaskRecord(
            id=10,
            session_id="s1",
            task_type="context_compaction",
            payload={},
            status="running",
            created_at=0.0,
        )
        result = await _run_context_compaction("s1", task, event_bus)
        assert result["skipped"] is True
        assert result["reason"] == "no chat_id"

    async def test_skip_when_chat_id_is_not_a_string(self) -> None:
        event_bus = MagicMock()
        task = IdleTaskRecord(
            id=12,
            session_id="s1",
            task_type="context_compaction",
            payload={"chat_id": 42},
            status="running",
            created_at=0.0,
        )
        result = await _run_context_compaction("s1", task, event_bus)
        assert result == {"skipped": True, "reason": "no chat_id"}
        event_bus.publish.assert_not_called()

    async def test_compaction_success_no_preheat(self) -> None:
        event_bus = MagicMock()
        task = IdleTaskRecord(
            id=11,
            session_id="s2",
            task_type="context_compaction",
            payload={"chat_id": "chat_123"},
            status="running",
            created_at=0.0,
        )
        compact_handler = AsyncMock(
            return_value={
                "compacted": True,
                "tokens_saved": 5000,
                "message_count": 20,
                "reason": "",
            }
        )
        register_context_compaction_handler(compact_handler)
        result = await _run_context_compaction("s2", task, event_bus)
        assert result == {"compacted": True, "chat_id": "chat_123"}
        compact_handler.assert_awaited_once_with("chat_123", "s2")
        published = [c.args[0] for c in event_bus.publish.call_args_list]
        assert [(e.status, e.task_name) for e in published] == [("working", "context_compaction")]

    async def test_compaction_not_needed(self) -> None:
        event_bus = MagicMock()
        task = IdleTaskRecord(
            id=12,
            session_id="s3",
            task_type="context_compaction",
            payload={"chat_id": "chat_short"},
            status="running",
            created_at=0.0,
        )
        compact_handler = AsyncMock(
            return_value={
                "compacted": False,
                "tokens_saved": 0,
                "message_count": 5,
                "reason": "too_few_messages",
            }
        )
        register_context_compaction_handler(compact_handler)
        result = await _run_context_compaction("s3", task, event_bus)
        assert result == {"compacted": False, "chat_id": "chat_short"}

    async def test_no_handler_registered(self) -> None:
        event_bus = MagicMock()
        task = IdleTaskRecord(
            id=13,
            session_id="s4",
            task_type="context_compaction",
            payload={"chat_id": "chat_456"},
            status="running",
            created_at=0.0,
        )
        result = await _run_context_compaction("s4", task, event_bus)
        assert result["compacted"] is False

    async def test_handler_error_caught(self) -> None:
        event_bus = MagicMock()
        task = IdleTaskRecord(
            id=14,
            session_id="s5",
            task_type="context_compaction",
            payload={"chat_id": "chat_err"},
            status="running",
            created_at=0.0,
        )
        compact_handler = AsyncMock(side_effect=RuntimeError("DB connection lost"))
        register_context_compaction_handler(compact_handler)
        result = await _run_context_compaction("s5", task, event_bus)
        assert result["compacted"] is False

    async def test_compaction_never_preheats_prefix_cache(self) -> None:
        """Idle compaction runs minutes after the provider cache TTL, so it must not re-warm it."""
        event_bus = MagicMock()
        task = IdleTaskRecord(
            id=15,
            session_id="s6",
            task_type="context_compaction",
            payload={"chat_id": "chat_preheat"},
            status="running",
            created_at=0.0,
        )
        compact_handler = AsyncMock(
            return_value={
                "compacted": True,
                "llm": AsyncMock(),
                "messages": [MagicMock()],
                "model_name": "anthropic/claude-3",
            }
        )
        register_context_compaction_handler(compact_handler)
        with patch(
            "myrm_agent_harness.agent.context_management.preheat.preheat_prefix_cache",
            new_callable=AsyncMock,
        ) as mock_preheat:
            result = await _run_context_compaction("s6", task, event_bus)
        assert result == {"compacted": True, "chat_id": "chat_preheat"}
        mock_preheat.assert_not_awaited()


@pytest.mark.asyncio
async def test_cognitive_subsumption_passes_consolidation_llm_by_signature() -> None:
    """The idle handler must call find_subsumed_memories with its real ``llm`` parameter."""
    registry = AsyncMock(spec=IdleTaskRegistry)
    registry.acquire_next.return_value = IdleTaskRecord(
        id=30,
        session_id="global",
        task_type="cognitive_subsumption",
        payload={"new_knowledge": "evolved skill body", "skill_id": "skill_1"},
        status="running",
        created_at=0.0,
    )
    consolidation_llm = MagicMock(spec=BaseChatModel)

    with (
        patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_maintenance_scheduler") as mock_sched,
        patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_event_bus") as mock_bus,
        patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_memory_manager") as mock_mm,
        patch(
            "myrm_agent_harness.toolkits.memory.strategies.subsumption.find_subsumed_memories",
            autospec=True,
            return_value=[],
        ) as mock_find,
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        scheduler = AsyncMock()
        scheduler.report_outcome = MagicMock()
        scheduler.request_capacity.return_value = CapacityTicket(ticket_id="t_sub", task_type="cognitive_subsumption")
        mock_sched.return_value = scheduler
        mock_bus.return_value = MagicMock()
        manager = MagicMock()
        manager._consolidation_llm = consolidation_llm
        mock_mm.return_value = manager

        await default_idle_callback("global", registry)

    mock_find.assert_awaited_once()
    assert mock_find.await_args.kwargs["llm"] is consolidation_llm
    registry.mark_completed.assert_awaited_once()
    registry.mark_error.assert_not_awaited()


@pytest.mark.asyncio
async def test_cognitive_subsumption_notification_carries_count_and_ids_not_text() -> None:
    task = IdleTaskRecord(
        id=31,
        session_id="global",
        task_type="cognitive_subsumption",
        payload={"new_knowledge": "evolved skill body"},
        status="running",
        created_at=0.0,
    )
    manager = MagicMock()
    manager._consolidation_llm = MagicMock(spec=BaseChatModel)

    events = await run_task_collecting_events(
        task,
        manager,
        (
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.subsumption.find_subsumed_memories",
                autospec=True,
                return_value=["m1", "m2"],
            ),
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.subsumption.apply_subsumption",
                autospec=True,
                return_value=2,
            ),
        ),
    )

    notification = next(e for e in events if e.status == "notification")
    assert notification.task_name == "cognitive_subsumption"
    assert notification.data is not None
    assert notification.data["count"] == 2
    assert notification.data["subsumed_ids"] == ["m1", "m2"]
    assert not any(hasattr(e, "message") for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("new_knowledge", [42, ["evolved skill body"], "", None])
async def test_cognitive_subsumption_skips_unusable_new_knowledge(new_knowledge: object) -> None:
    task = IdleTaskRecord(
        id=32,
        session_id="global",
        task_type="cognitive_subsumption",
        payload={"new_knowledge": new_knowledge},
        status="running",
        created_at=0.0,
    )
    manager = MagicMock()
    manager._consolidation_llm = MagicMock(spec=BaseChatModel)
    find_patch = patch(
        "myrm_agent_harness.toolkits.memory.strategies.subsumption.find_subsumed_memories",
        autospec=True,
        return_value=[],
    )

    with find_patch as mock_find:
        events = await run_task_collecting_events(task, manager)

    mock_find.assert_not_awaited()
    assert not any(e.status == "notification" for e in events)


@pytest.mark.asyncio
async def test_unknown_task_type_is_completed_with_an_unhandled_result() -> None:
    registry = AsyncMock(spec=IdleTaskRegistry)

    events = await run_task_collecting_events(idle_record("retired_task", task_id=40), MagicMock(), registry=registry)

    registry.mark_completed.assert_awaited_once_with(40)
    registry.mark_error.assert_not_awaited()
    completed = next(e for e in events if e.status == "completed")
    assert completed.data == {"unhandled": True}


@pytest.mark.asyncio
async def test_context_compaction_task_runs_the_registered_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = AsyncMock(return_value={"compacted": True})
    monkeypatch.setattr(idle_tasks, "_context_compaction_handler", handler)
    registry = AsyncMock(spec=IdleTaskRegistry)

    events = await run_task_collecting_events(
        idle_record("context_compaction", {"chat_id": "chat_9"}, task_id=41), MagicMock(), registry=registry
    )

    handler.assert_awaited_once_with("chat_9", "global")
    registry.mark_completed.assert_awaited_once_with(41)
    completed = next(e for e in events if e.status == "completed")
    assert completed.data == {"compacted": True, "chat_id": "chat_9"}


@pytest.mark.asyncio
async def test_cognitive_subsumption_without_consolidation_llm_is_skipped() -> None:
    registry = AsyncMock(spec=IdleTaskRegistry)
    manager = MagicMock()
    manager._consolidation_llm = None

    events = await run_task_collecting_events(
        idle_record("cognitive_subsumption", {"new_knowledge": "evolved skill body"}, task_id=44),
        manager,
        registry=registry,
    )

    registry.mark_completed.assert_awaited_once_with(44)
    completed = next(e for e in events if e.status == "completed")
    assert completed.data == {"skipped": True, "reason": "No consolidation_llm configured"}


@pytest.mark.asyncio
async def test_pending_task_is_not_acquired_while_a_cooperative_pause_is_active() -> None:
    registry = AsyncMock(spec=IdleTaskRegistry)
    pause_signal = MagicMock(is_pause_requested=True, pause_reason="user typing")

    with patch(
        "myrm_agent_harness.agent.background_worker.idle_tasks.get_global_pause_signal", return_value=pause_signal
    ):
        ran = await default_idle_callback("global", registry)

    assert ran is False
    registry.acquire_next.assert_not_awaited()
