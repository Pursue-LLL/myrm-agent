"""Driver of the idle-task handler tests: one task through the idle callback with its collaborators stubbed.

[INPUT]
- agent.background_worker.idle_tasks::default_idle_callback (POS: Runs one pending idle task and publishes its progress events)
- agent.background_worker.registry::IdleTaskRecord, IdleTaskRegistry (POS: Crash-resilient idle task queue)
- runtime.events.idle_events::IdleTaskProgressEvent (POS: Idle task progress event on the harness bus)
- runtime.maintenance.protocols::CapacityTicket (POS: Capacity grant of the maintenance scheduler)

[OUTPUT]
- idle_record: a running idle task record for a task type and payload
- run_task_collecting_events: run one task through the callback and return every event it published

[POS]
Harness pytest-only driver shared by the idle-task handler tests. The scheduler grants capacity, the event bus is a
recorder, and the memory manager is whatever the test hands in, so a test states the task and the manager and reads
the registry calls and the events, not the plumbing.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

from myrm_agent_harness.agent.background_worker.idle_tasks import default_idle_callback
from myrm_agent_harness.agent.background_worker.registry import IdleTaskRecord, IdleTaskRegistry
from myrm_agent_harness.runtime.events.idle_events import IdleTaskProgressEvent
from myrm_agent_harness.runtime.maintenance.protocols import CapacityTicket


def idle_record(task_type: str, payload: dict[str, object] | None = None, task_id: int = 50) -> IdleTaskRecord:
    """A running global-queue task of ``task_type``."""
    return IdleTaskRecord(
        id=task_id,
        session_id="global",
        task_type=task_type,
        payload=payload or {},
        status="running",
        created_at=0.0,
    )


async def run_task_collecting_events(
    task: IdleTaskRecord,
    manager: MagicMock | None,
    extra_patches: tuple[object, ...] = (),
    registry: AsyncMock | None = None,
) -> list[IdleTaskProgressEvent]:
    """Run one idle task through ``default_idle_callback`` and return every published event."""
    registry = registry or AsyncMock(spec=IdleTaskRegistry)
    registry.acquire_next.return_value = task
    scheduler = AsyncMock()
    scheduler.report_outcome = MagicMock()
    scheduler.request_capacity.return_value = CapacityTicket(ticket_id="t", task_type=task.task_type)
    event_bus = MagicMock()

    with (
        patch(
            "myrm_agent_harness.agent.background_worker.idle_tasks.get_maintenance_scheduler", return_value=scheduler
        ),
        patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_event_bus", return_value=event_bus),
        patch("myrm_agent_harness.agent.background_worker.idle_tasks.get_memory_manager", return_value=manager),
        patch("asyncio.sleep", new_callable=AsyncMock),
        ExitStack() as stack,
    ):
        for extra in extra_patches:
            stack.enter_context(extra)
        await default_idle_callback(task.session_id, registry)

    return [c.args[0] for c in event_bus.publish.call_args_list]
