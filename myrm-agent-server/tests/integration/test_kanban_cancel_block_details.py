"""An agent that cancels a blocked task leaves it without the block's reason, kind and wake-up time.

Runs the orchestrator's real ``kanban_cancel_task`` tool against the real service and SQLite store: the cancelled task
is archived, and an archived card must not keep a reason or a countdown for a block that no longer exists.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.kanban.types import BlockKind, TaskStatus

from app.services.kanban import KanbanService

if TYPE_CHECKING:
    from app.ai_agents.general_agent import GeneralAgent


@pytest.fixture(autouse=True)
def _reset_kanban_singleton() -> Iterator[None]:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> Iterator[None]:
    with patch.object(KanbanService, "_validate_agent_id", new_callable=AsyncMock):
        yield


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("block_kind", [BlockKind.HUMAN, BlockKind.SCHEDULED])
async def test_cancelling_a_blocked_task_archives_it_without_block_details(block_kind: BlockKind) -> None:
    from app.ai_agents.general_agent.factory import _setup_kanban_tools

    svc = KanbanService.get_instance()
    board = await svc.create_board("Cancel Board")
    created = await svc.add_task(board.board_id, "Waiting for the client")
    wake_at = datetime.now(UTC) + timedelta(hours=2) if block_kind is BlockKind.SCHEDULED else None
    await svc.move_task(
        created.task_id,
        TaskStatus.BLOCKED,
        block_kind=block_kind,
        blocked_reason="Waiting for the client's answer",
        scheduled_until=wake_at,
    )

    tools: list[BaseTool] = []
    agent = cast(
        "GeneralAgent",
        SimpleNamespace(kanban_tool_mode="orchestrator", kanban_current_task_id=None, agent_id="agent-cancel"),
    )
    await _setup_kanban_tools(agent, tools)
    cancel = next(tool for tool in tools if tool.name == "kanban_cancel_task")

    reply = json.loads(await cancel.ainvoke({"task_id": created.task_id, "reason": "no longer needed"}))

    assert "error" not in reply
    cancelled = await svc.get_task(created.task_id)
    assert cancelled is not None
    assert cancelled.status is TaskStatus.ARCHIVED
    assert (cancelled.blocked_reason, cancelled.block_kind, cancelled.scheduled_until) == (None, None, None)
