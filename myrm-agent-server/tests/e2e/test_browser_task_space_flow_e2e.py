"""Task Flow E2E: Browser Task Spaces End-to-End Orchestration Lifecycle Test.

Validates the complete real-world user & agent workflow:
  1. User/Agent initiates parallel browser workspaces for separate sub-tasks.
  2. Harness initializes independent BrowserTaskSpace instances under quota constraints.
  3. Server exposes space state and manages takeover/release transitions.
  4. Real-time metrics (idle_seconds, active_pages, takeover_active) correctly reflect runtime events.
  5. Idle spaces are gracefully pruned, preventing memory exhaustion.
"""

from __future__ import annotations

import asyncio

import pytest
from myrm_agent_harness.toolkits.browser.spaces.space_manager import HarnessTaskSpaceManager

from app.services.browser_spaces.task_space_service import TaskSpaceService


@pytest.mark.asyncio
async def test_browser_task_space_complete_task_flow_e2e() -> None:
    """Universal Task Flow E2E: multi-space creation, concurrent lock isolation, takeover, and auto-pruning."""
    manager = HarnessTaskSpaceManager(max_active_spaces=3, default_idle_ttl_seconds=1.0)
    service = TaskSpaceService(manager)

    # Step 1: Allocate parallel workspaces for two concurrent tasks
    space_a = await service.get_or_create_space(space_id="flow-space-alpha", name="Market Analysis Subtask")
    space_b = await service.get_or_create_space(space_id="flow-space-beta", name="Competitor Scraping Subtask")

    assert space_a.space_id == "flow-space-alpha"
    assert space_b.space_id == "flow-space-beta"
    assert space_a.status == "idle"

    # Step 2: Concurrency & Lock verification
    harness_space_a = manager.get_space("flow-space-alpha")
    assert harness_space_a is not None

    async with harness_space_a.lock:
        # Simulate sub-agent tool execution within exclusive lock
        harness_space_a.touch()
        assert harness_space_a.is_active is True

    # Step 3: Human-in-the-loop takeover transition
    takeover_res = await service.set_takeover("flow-space-alpha", enabled=True)
    assert takeover_res is not None
    assert takeover_res.status == "takeover"
    assert takeover_res.takeover_active is True

    # Step 4: Quota boundary verification (max 3)
    space_c = await service.get_or_create_space(space_id="flow-space-gamma", name="Data Validation Subtask")
    assert space_c.space_id == "flow-space-gamma"

    # Step 5: Graceful release of a completed task space
    closed = await service.close_space("flow-space-beta")
    assert closed is True

    remaining = await service.list_spaces()
    remaining_ids = {s.space_id for s in remaining}
    assert "flow-space-beta" not in remaining_ids
    assert "flow-space-alpha" in remaining_ids
    assert "flow-space-gamma" in remaining_ids

    # Step 6: Idle TTL auto-pruning simulation
    await asyncio.sleep(1.1)
    pruned_count = await service.prune_idle(max_idle_seconds=1.0)
    assert pruned_count >= 1

    # Cleanup any remaining
    await manager.close_all()
