"""Board summary aggregation for KanbanService.

[INPUT]
- myrm_agent_harness.toolkits.kanban.dispatcher (POS: Kanban dispatcher framework.)
- core.kanban.adapters::SqlAlchemyKanbanStore (POS: KanbanStore persistence adapter.)
- service_types (POS: Kanban service shared types.)

[OUTPUT]
- gather_summary, build_board_summary

[POS]
Board-level summary aggregation: status counts, agent distribution, oldest ready age.
"""

from __future__ import annotations

import asyncio

from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher

from app.core.kanban.adapters import SqlAlchemyKanbanStore
from app.services.kanban.service_types import BoardSummaryData


async def gather_summary(
    store: SqlAlchemyKanbanStore,
    board_id: str,
) -> tuple[dict[str, int], dict[str | None, dict[str, int]], int | None]:
    """Fetch status counts, by-agent distribution, and oldest ready age concurrently."""
    status_counts, by_agent, oldest_age = await asyncio.gather(
        store.count_tasks_grouped(board_id),
        store.count_tasks_by_agent(board_id),
        store.oldest_ready_age_seconds(board_id),
    )
    return status_counts, by_agent, oldest_age


async def build_board_summary(
    store: SqlAlchemyKanbanStore,
    dispatchers: dict[str, KanbanDispatcher],
    board_id: str,
) -> BoardSummaryData | None:
    board = await store.get_board(board_id)
    if board is None:
        return None

    status_counts, by_agent, oldest_age = await gather_summary(store, board_id)

    return BoardSummaryData(
        board=board,
        task_counts=status_counts,
        total_tasks=sum(status_counts.values()),
        dispatcher_active=board_id in dispatchers and dispatchers[board_id].is_running,
        by_agent=by_agent,
        oldest_ready_age_seconds=oldest_age,
    )
