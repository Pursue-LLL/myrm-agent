"""[INPUT]
- .common (POS: shared types and helpers)

[OUTPUT]
- DependenciesMixin

[POS]
SqlAlchemyKanbanStore mixin: dependency edges (DAG): cycle check, add/remove edge, parents/children, readiness.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban.types import (
    _TERMINAL_STATUSES,
    TaskEdge,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, select

from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanTaskEdgeModel,
    KanbanTaskModel,
)

from .common import (
    _exec_rowcount,
)


class DependenciesMixin:
    async def _would_create_cycle(
        self,
        parent_id: str,
        child_id: str,
    ) -> bool:
        """DFS via parent chain to detect if adding edge would create a cycle."""
        if parent_id == child_id:
            return True
        async with get_session() as session:
            stmt = select(
                KanbanTaskEdgeModel.child_task_id,
                KanbanTaskEdgeModel.parent_task_id,
            )
            result = await session.execute(stmt)
            adj: dict[str, list[str]] = {}
            for c_id, p_id in result.all():
                adj.setdefault(c_id, []).append(p_id)

        visited: set[str] = set()
        stack = [parent_id]
        while stack:
            node = stack.pop()
            if node == child_id:
                return True
            if node in visited:
                continue
            visited.add(node)
            stack.extend(adj.get(node, []))
        return False

    async def add_edge(self, parent_task_id: str, child_task_id: str) -> TaskEdge:
        if await self._would_create_cycle(parent_task_id, child_task_id):
            raise ValueError(f"Adding edge {parent_task_id} -> {child_task_id} would create a cycle")
        async with get_session() as session:
            existing = await session.execute(
                select(KanbanTaskEdgeModel).where(
                    KanbanTaskEdgeModel.parent_task_id == parent_task_id,
                    KanbanTaskEdgeModel.child_task_id == child_task_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                return TaskEdge(parent_task_id=parent_task_id, child_task_id=child_task_id)

            m = KanbanTaskEdgeModel(
                parent_task_id=parent_task_id,
                child_task_id=child_task_id,
            )
            session.add(m)
            await session.commit()
        return TaskEdge(parent_task_id=parent_task_id, child_task_id=child_task_id)

    async def remove_edge(self, parent_task_id: str, child_task_id: str) -> bool:
        async with get_session() as session:
            stmt = sql_delete(KanbanTaskEdgeModel).where(
                KanbanTaskEdgeModel.parent_task_id == parent_task_id,
                KanbanTaskEdgeModel.child_task_id == child_task_id,
            )
            result = await session.execute(stmt)
            await session.commit()
            return _exec_rowcount(result) > 0

    async def list_parents(self, task_id: str) -> list[str]:
        async with get_session() as session:
            stmt = select(KanbanTaskEdgeModel.parent_task_id).where(KanbanTaskEdgeModel.child_task_id == task_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_children(self, task_id: str) -> list[str]:
        async with get_session() as session:
            stmt = select(KanbanTaskEdgeModel.child_task_id).where(KanbanTaskEdgeModel.parent_task_id == task_id)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_board_edges(self, board_id: str) -> list[TaskEdge]:
        """Return all edges for tasks belonging to the given board."""
        async with get_session() as session:
            stmt = (
                select(
                    KanbanTaskEdgeModel.parent_task_id,
                    KanbanTaskEdgeModel.child_task_id,
                )
                .join(
                    KanbanTaskModel,
                    KanbanTaskEdgeModel.parent_task_id == KanbanTaskModel.id,
                )
                .where(KanbanTaskModel.board_id == board_id)
            )
            result = await session.execute(stmt)
            return [TaskEdge(parent_task_id=row[0], child_task_id=row[1]) for row in result.all()]

    async def are_dependencies_met(self, task_id: str) -> bool:
        async with get_session() as session:
            has_unmet = await session.execute(
                select(
                    exists().where(
                        KanbanTaskEdgeModel.child_task_id == task_id,
                        KanbanTaskEdgeModel.parent_task_id == KanbanTaskModel.id,
                        KanbanTaskModel.status.notin_([s.value for s in _TERMINAL_STATUSES]),
                    )
                )
            )
            return not has_unmet.scalar_one()
