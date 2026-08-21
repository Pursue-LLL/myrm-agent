"""Unit and integration tests for Capacity Theater Memory Doctor probe and Disciplined Defaults restoration.

[INPUT]
app.services.memory.diagnostics.diagnostic.diagnostic_static_checks::probe_capacity_theater
app.api.memory.operations.command_center_actions::run_restore_disciplined_defaults
app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor::MemoryDiagnosticRepairExecutor

[OUTPUT]
test_capacity_theater_probe_clean, test_capacity_theater_probe_bloated, test_restore_disciplined_defaults_execution

[POS]
Integration tests proving capacity theater detection and zero-data-loss safe archive restoration.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.memory import MemoryType
from myrm_agent_harness.toolkits.memory.types import MemoryStatus

from app.api.memory.operations.command_center_actions import run_restore_disciplined_defaults
from app.schemas.memory.command_center import MemoryCommandActionRequest
from app.services.memory.diagnostics.diagnostic.diagnostic_static_checks import probe_capacity_theater


def test_capacity_theater_probe_clean() -> None:
    """Verify clean memory stack returns ready status and no auto fix."""
    check = probe_capacity_theater(
        total_active_chars=1200,
        working_memory_count=5,
        unpinned_count=10,
        budget_limit=6000,
    )
    assert check.id == "capacity_theater"
    assert check.status == "ready"
    assert check.can_auto_fix is False
    assert check.repair_actions == []


def test_capacity_theater_probe_bloated() -> None:
    """Verify bloated memory stack returns warning status and restore repair action."""
    check = probe_capacity_theater(
        total_active_chars=7500,
        working_memory_count=45,
        unpinned_count=60,
        budget_limit=6000,
    )
    assert check.id == "capacity_theater"
    assert check.status == "warning"
    assert check.can_auto_fix is True
    assert "restore_disciplined_defaults" in check.repair_actions


@pytest.mark.asyncio
async def test_restore_disciplined_defaults_execution() -> None:
    """Verify restore_disciplined_defaults archives unpinned memories while preserving pinned ones."""
    mock_db = AsyncMock()
    mock_manager = MagicMock()

    mem_pinned = MagicMock()
    mem_pinned.id = "mem-1"
    mem_pinned.is_pinned = True

    mem_unpinned = MagicMock()
    mem_unpinned.id = "mem-2"
    mem_unpinned.is_pinned = False

    mock_manager.list_memories = AsyncMock(
        side_effect=lambda mtype, limit: [mem_pinned, mem_unpinned] if mtype == MemoryType.TASK_DIGEST else []
    )
    mock_manager.update_memory = AsyncMock()

    body = MemoryCommandActionRequest(target_kind="memory", action="restore_defaults")
    res = await run_restore_disciplined_defaults(body, mock_db, mock_manager)

    assert "archived 1 memories" in res
    assert "preserved 1 pinned entries" in res
    mock_manager.update_memory.assert_awaited_once_with("mem-2", status=MemoryStatus.ARCHIVED)
