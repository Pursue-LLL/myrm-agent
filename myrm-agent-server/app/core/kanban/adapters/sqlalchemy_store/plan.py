"""[INPUT]
- .common (POS: shared types and helpers)

[OUTPUT]
- PlanMixin

[POS]
SqlAlchemyKanbanStore mixin: plan revision and agent-reference cleanup.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.kanban.protocols import PlanRevisionOutcome, PlanRevisionSpec
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
    TaskPriority,
    TaskStatus,
)
from sqlalchemy import delete as sql_delete
from sqlalchemy import or_, select, update

from app.core.kanban.adapters.sqlalchemy_mapping import (
    task_to_model,
)
from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanTaskEdgeModel,
    KanbanTaskEventModel,
    KanbanTaskModel,
)

from .common import (
    _exec_rowcount,
)


class PlanMixin:
    async def revise_plan(self, spec: PlanRevisionSpec) -> PlanRevisionOutcome:
        """Atomically revise board tasks and DAG edges within a single DB transaction."""
        async with get_session() as session:
            # 1. Validate completed task immutability
            for item in spec.task_changes:
                if item.action in ("remove", "update") and item.task_id:
                    existing_model = await session.get(KanbanTaskModel, item.task_id)
                    if existing_model and existing_model.status in (
                        TaskStatus.COMPLETED.value,
                        TaskStatus.IN_REVIEW.value,
                    ):
                        return PlanRevisionOutcome(
                            ok=False,
                            board_id=spec.board_id,
                            reason=f"Cannot modify task {item.task_id} in {existing_model.status} status",
                        )

            # 2. Query existing board edges to build shadow edge graph for cycle detection
            edge_stmt = (
                select(
                    KanbanTaskEdgeModel.parent_task_id,
                    KanbanTaskEdgeModel.child_task_id,
                )
                .join(
                    KanbanTaskModel,
                    KanbanTaskEdgeModel.parent_task_id == KanbanTaskModel.id,
                )
                .where(KanbanTaskModel.board_id == spec.board_id)
            )
            existing_edges_res = await session.execute(edge_stmt)
            shadow_edges: list[tuple[str, str]] = [(r[0], r[1]) for r in existing_edges_res.all()]

            # Remove specified edges
            for p_id, c_id in spec.remove_edges:
                shadow_edges = [e for e in shadow_edges if not (e[0] == p_id and e[1] == c_id)]

            # Clean cascade edges for removed tasks
            removed_task_ids_set = {item.task_id for item in spec.task_changes if item.action == "remove" and item.task_id}
            if removed_task_ids_set:
                shadow_edges = [e for e in shadow_edges if e[0] not in removed_task_ids_set and e[1] not in removed_task_ids_set]

            # Add new edges
            for p_id, c_id in spec.add_edges:
                if (p_id, c_id) not in shadow_edges:
                    shadow_edges.append((p_id, c_id))

            # Cycle detection on shadow_edges
            adj: dict[str, list[str]] = {}
            for p_id, c_id in shadow_edges:
                adj.setdefault(c_id, []).append(p_id)

            visited: dict[str, int] = {}
            all_nodes = set(adj.keys())
            for parents in adj.values():
                all_nodes.update(parents)

            def dfs(node: str) -> bool:
                visited[node] = 1
                for neighbor in adj.get(node, []):
                    if visited.get(neighbor, 0) == 1:
                        return True
                    if visited.get(neighbor, 0) == 0 and dfs(neighbor):
                        return True
                visited[node] = 2
                return False

            for n in all_nodes:
                if visited.get(n, 0) == 0:
                    if dfs(n):
                        return PlanRevisionOutcome(
                            ok=False,
                            board_id=spec.board_id,
                            reason="Plan revision would create a dependency cycle",
                        )

            # 3. Apply mutations in DB
            added_tids: list[str] = []
            updated_tids: list[str] = []
            removed_tids: list[str] = []

            for item in spec.task_changes:
                if item.action == "add":
                    tid = item.task_id or uuid.uuid4().hex[:12]
                    try:
                        prio = TaskPriority(item.priority)
                    except ValueError:
                        prio = TaskPriority.NORMAL
                    deps = list(item.depends_on)
                    initial_status = TaskStatus.BACKLOG if deps else TaskStatus.READY
                    new_task = KanbanTask(
                        task_id=tid,
                        board_id=spec.board_id,
                        title=item.title or "Untitled Task",
                        description=item.description or "",
                        status=initial_status,
                        priority=prio,
                        agent_id=item.agent_id,
                        model_override=item.model_override,
                        extra_skill_ids=list(item.extra_skill_ids),
                    )
                    session.add(task_to_model(new_task))
                    added_tids.append(tid)

                elif item.action == "update" and item.task_id:
                    m = await session.get(KanbanTaskModel, item.task_id)
                    if m:
                        if item.title is not None:
                            m.title = item.title
                        if item.description is not None:
                            m.description = item.description
                        if item.agent_id is not None:
                            m.agent_id = item.agent_id
                        if item.model_override is not None:
                            m.model_override = item.model_override
                        if item.extra_skill_ids:
                            m.extra_skill_ids_json = list(item.extra_skill_ids)
                        m.updated_at = datetime.now(UTC)
                        updated_tids.append(m.id)

                elif item.action == "remove" and item.task_id:
                    m = await session.get(KanbanTaskModel, item.task_id)
                    if m:
                        m.status = TaskStatus.ARCHIVED.value
                        m.blocked_reason = m.block_kind = m.scheduled_until = None
                        m.completed_at = datetime.now(UTC)
                        m.updated_at = datetime.now(UTC)
                        # Cascade clean edges from DB
                        await session.execute(
                            sql_delete(KanbanTaskEdgeModel).where(
                                or_(
                                    KanbanTaskEdgeModel.parent_task_id == item.task_id,
                                    KanbanTaskEdgeModel.child_task_id == item.task_id,
                                )
                            )
                        )
                        removed_tids.append(m.id)

            # Flush tasks before adding edges to ensure foreign keys resolve
            await session.flush()

            # Add implicit edges from depends_on in added tasks
            for item in spec.task_changes:
                if item.action == "add" and item.depends_on:
                    child_tid = item.task_id or ""
                    for pid in item.depends_on:
                        edge_exist = await session.execute(
                            select(KanbanTaskEdgeModel).where(
                                KanbanTaskEdgeModel.parent_task_id == pid,
                                KanbanTaskEdgeModel.child_task_id == child_tid,
                            )
                        )
                        if edge_exist.scalar_one_or_none() is None:
                            session.add(KanbanTaskEdgeModel(parent_task_id=pid, child_task_id=child_tid))

            await session.flush()

            # Explicit remove edges
            for p_id, c_id in spec.remove_edges:
                await session.execute(
                    sql_delete(KanbanTaskEdgeModel).where(
                        KanbanTaskEdgeModel.parent_task_id == p_id,
                        KanbanTaskEdgeModel.child_task_id == c_id,
                    )
                )

            # Explicit add edges
            for p_id, c_id in spec.add_edges:
                edge_exist = await session.execute(
                    select(KanbanTaskEdgeModel).where(
                        KanbanTaskEdgeModel.parent_task_id == p_id,
                        KanbanTaskEdgeModel.child_task_id == c_id,
                    )
                )
                if edge_exist.scalar_one_or_none() is None:
                    session.add(KanbanTaskEdgeModel(parent_task_id=p_id, child_task_id=c_id))

            await session.flush()

            # Audit events
            for tid in added_tids + updated_tids + removed_tids:
                event = KanbanTaskEventModel(
                    task_id=tid,
                    kind=TaskEventKind.PLAN_REVISED.value,
                    payload_json={
                        "board_id": spec.board_id,
                        "rationale": spec.rationale,
                        "author": spec.author,
                        "added_count": len(added_tids),
                        "updated_count": len(updated_tids),
                        "removed_count": len(removed_tids),
                    },
                    created_at=datetime.now(UTC),
                )
                session.add(event)

            await session.commit()

        return PlanRevisionOutcome(
            ok=True,
            board_id=spec.board_id,
            reason="applied",
            added_task_ids=tuple(added_tids),
            updated_task_ids=tuple(updated_tids),
            removed_task_ids=tuple(removed_tids),
            added_edges=tuple(spec.add_edges),
            removed_edges=tuple(spec.remove_edges),
            persisted=True,
        )

    async def clear_agent_references(self, agent_id: str) -> int:
        """Set agent_id to NULL on all tasks referencing the given agent."""
        async with get_session() as session:
            stmt = update(KanbanTaskModel).where(KanbanTaskModel.agent_id == agent_id).values(agent_id=None)
            result = await session.execute(stmt)
            await session.commit()
            return _exec_rowcount(result)
