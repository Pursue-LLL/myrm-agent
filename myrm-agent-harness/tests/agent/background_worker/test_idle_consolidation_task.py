"""The ``cognitive_consolidation`` idle task: one forced maintenance cycle, and what each outcome does to the task."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.background_worker.idle_tasks import default_idle_callback
from myrm_agent_harness.agent.background_worker.registry import IdleTaskRecord, IdleTaskRegistry
from myrm_agent_harness.runtime.cognitive_clock.signals import get_global_pause_signal
from myrm_agent_harness.runtime.events.idle_events import IdleTaskProgressEvent
from myrm_agent_harness.runtime.maintenance.protocols import CapacityTicket
from myrm_agent_harness.toolkits.memory.health import MaintenanceReport
from tests.support.idle_task_runner import idle_record, run_task_collecting_events


@pytest.mark.asyncio
@patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_maintenance_scheduler")
@patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_memory_manager")
async def test_consolidation_cycle_completes_with_a_counts_only_summary(mock_get_memory_manager, mock_get_scheduler):
    # Setup scheduler mock
    mock_scheduler = AsyncMock()
    mock_scheduler.report_outcome = MagicMock()
    mock_ticket = CapacityTicket(ticket_id="test_ticket", task_type="cognitive_consolidation")
    mock_scheduler.request_capacity.return_value = mock_ticket
    mock_get_scheduler.return_value = mock_scheduler

    # Setup EventBus mock
    mock_event_bus = MagicMock()
    with patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_event_bus", return_value=mock_event_bus):
        # The maintenance report carries memory text (insights, neglected previews) that the event must not.
        mock_memory_manager = MagicMock()
        mock_memory_manager.run_maintenance_cycle = AsyncMock(
            return_value=MaintenanceReport(
                consolidation_merged=2,
                consolidation_corrected=1,
                consolidation_updated=3,
                forgotten_count=4,
                archived_count=5,
                duration_ms=12.5,
                insights=("the user avoids meetings before noon",),
            )
        )
        mock_get_memory_manager.return_value = mock_memory_manager

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

        session_id = "test_session_3"

        # Mock asyncio.sleep to speed up tests
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await default_idle_callback(session_id, mock_registry)

        # Assertions
        mock_scheduler.request_capacity.assert_called_once()
        mock_scheduler.release_capacity.assert_called_once_with(mock_ticket)
        mock_registry.acquire_next.assert_called_once_with(session_id)
        mock_registry.mark_completed.assert_called_once_with(1)

        # Verify events published
        published_events = [call.args[0] for call in mock_event_bus.publish.call_args_list]
        assert len(published_events) == 4
        assert all(isinstance(e, IdleTaskProgressEvent) for e in published_events)

        assert published_events[0].status == "working"
        assert published_events[0].progress_pct == 10

        assert published_events[1].status == "working"
        assert published_events[1].progress_pct == 50

        assert published_events[2].status == "completed"
        assert published_events[2].progress_pct == 100
        assert published_events[2].data == {
            "consolidation": {"merged": 2, "corrected": 1, "updated": 3, "errors": 0},
            "forgetting": {"forgotten": 4, "archived": 5},
            "duration_ms": 12.5,
            "skipped": False,
            "skip_reason": "",
            "interrupted_by_pause": False,
        }
        # A foreground keystroke must be able to stop the cycle, so the process-wide pause signal travels with it.
        mock_memory_manager.run_maintenance_cycle.assert_awaited_once_with(
            force=True, pause_signal=get_global_pause_signal()
        )

        assert published_events[3].status == "idle"

        # Presentation text belongs to the UI layer; events carry structure only.
        assert not any(hasattr(e, "message") for e in published_events)


@pytest.mark.asyncio
async def test_consolidation_without_memory_manager_is_simulated() -> None:
    registry = AsyncMock(spec=IdleTaskRegistry)

    events = await run_task_collecting_events(
        idle_record("cognitive_consolidation", task_id=42), None, registry=registry
    )

    registry.mark_completed.assert_awaited_once_with(42)
    assert next(e for e in events if e.status == "completed").data == {"simulated": True}


@pytest.mark.asyncio
async def test_consolidation_errors_mark_the_task_failed() -> None:
    registry = AsyncMock(spec=IdleTaskRegistry)
    manager = MagicMock()
    manager.run_maintenance_cycle = AsyncMock(return_value=MaintenanceReport(consolidation_errors=2))

    events = await run_task_collecting_events(
        idle_record("cognitive_consolidation", task_id=43), manager, registry=registry
    )

    registry.mark_error.assert_awaited_once_with(43)
    registry.mark_completed.assert_not_awaited()
    assert any(e.status == "error" for e in events)


@pytest.mark.asyncio
async def test_consolidation_interrupted_by_foreground_activity_is_requeued_not_completed() -> None:
    registry = AsyncMock(spec=IdleTaskRegistry)
    # The pause can land after a consolidation stage that already counted errors; the interruption still wins.
    manager = MagicMock()
    manager.run_maintenance_cycle = AsyncMock(
        return_value=MaintenanceReport(
            skipped=True, skip_reason="user_sent_message", interrupted_by_pause=True, consolidation_errors=1
        )
    )

    events = await run_task_collecting_events(
        idle_record("cognitive_consolidation", task_id=45), manager, registry=registry
    )

    registry.requeue.assert_awaited_once_with(45)
    registry.mark_completed.assert_not_awaited()
    registry.mark_error.assert_not_awaited()
    assert not any(e.status == "completed" for e in events)
    assert events[-1].status == "idle"
