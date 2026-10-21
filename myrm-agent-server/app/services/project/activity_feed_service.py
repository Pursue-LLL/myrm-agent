"""Project activity feed service.

[INPUT]
- database.session::get_session (POS: SQLAlchemy session accessor.)
- database.models.kanban::KanbanBoardModel, KanbanTaskModel (POS: Kanban boards and tasks models.)
- database.models.cron::CronJobModel, CronRunModel (POS: Cron jobs and runs models.)
- database.models.milestone::ProjectMilestone (POS: Milestone models.)

[OUTPUT]
- ProjectActivityFeedService: Aggregates project-level activity feed (handoffs, task completion, cron runs, milestones).
- ProjectActivityItem: Strongly-typed Pydantic model for activity events.

[POS]
Team collaboration feed service for local projects. Consolidates disparate task handoffs,
state changes, cron runs, and milestone achievements into a chronological timeline feed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from app.database.connection import get_session
from app.database.models.cron import CronJobModel, CronRunModel
from app.database.models.kanban import KanbanBoardModel, KanbanTaskModel
from app.database.models.milestone import Milestone

ActivityKind = Literal[
    "task_handoff",
    "task_completed",
    "task_blocked",
    "task_created",
    "cron_run",
    "milestone_created",
]


class ProjectActivityItem(BaseModel):
    id: str
    kind: ActivityKind
    title: str
    detail: str = ""
    actor: str = "system"
    timestamp: datetime
    metadata: dict[str, object] = Field(default_factory=dict)


class ProjectActivityFeedResponse(BaseModel):
    project_id: str
    items: list[ProjectActivityItem]
    total: int


class ProjectActivityFeedService:
    """Aggregates chronological timeline activity across tasks, handoffs, crons, and milestones."""

    @staticmethod
    async def get_activity_feed(
        project_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> ProjectActivityFeedResponse:
        items: list[ProjectActivityItem] = []

        async with get_session() as db:
            # 1. Fetch boards for this project
            boards_stmt = select(KanbanBoardModel.id).where(KanbanBoardModel.project_id == project_id)
            board_ids = (await db.execute(boards_stmt)).scalars().all()

            if board_ids:
                # Fetch tasks on these boards
                tasks_stmt = (
                    select(KanbanTaskModel)
                    .where(KanbanTaskModel.board_id.in_(board_ids))
                    .order_by(desc(KanbanTaskModel.updated_at))
                    .limit(100)
                )
                tasks = (await db.execute(tasks_stmt)).scalars().all()

                for task in tasks:
                    meta = task.metadata if isinstance(task.metadata, dict) else {}

                    # Check handoff history
                    raw_history = meta.get("handoff_history")
                    handoff_list: list[dict[str, object]] = []
                    if isinstance(raw_history, list):
                        handoff_list = [h for h in raw_history if isinstance(h, dict)]
                    elif isinstance(meta.get("handoff"), dict):
                        handoff_list = [meta["handoff"]]

                    for idx, h in enumerate(handoff_list):
                        ts_str = str(h.get("timestamp") or "")
                        try:
                            ts = datetime.fromisoformat(ts_str) if ts_str else task.updated_at
                        except Exception:
                            ts = task.updated_at

                        from_agent = str(h.get("from_agent_id") or "Unassigned")
                        to_agent = str(h.get("to_agent_id") or "Next Assignee")
                        summary = str(h.get("summary") or "")

                        items.append(
                            ProjectActivityItem(
                                id=f"handoff-{task.id}-{idx}",
                                kind="task_handoff",
                                title=f"Task handed off: {task.title}",
                                detail=summary or f"{from_agent} -> {to_agent}",
                                actor=to_agent,
                                timestamp=ts,
                                metadata={
                                    "task_id": task.id,
                                    "board_id": task.board_id,
                                    "from_agent_id": from_agent,
                                    "to_agent_id": to_agent,
                                    "changed_files": h.get("changed_files") or [],
                                },
                            )
                        )

                    # Task completed
                    if task.status == "completed":
                        items.append(
                            ProjectActivityItem(
                                id=f"task-completed-{task.id}",
                                kind="task_completed",
                                title=f"Task completed: {task.title}",
                                detail=task.result or "",
                                actor=task.agent_id or "agent",
                                timestamp=task.updated_at or task.created_at,
                                metadata={"task_id": task.id, "board_id": task.board_id},
                            )
                        )
                    elif task.status == "blocked":
                        items.append(
                            ProjectActivityItem(
                                id=f"task-blocked-{task.id}",
                                kind="task_blocked",
                                title=f"Task blocked: {task.title}",
                                detail=task.blocked_reason or "",
                                actor=task.agent_id or "system",
                                timestamp=task.updated_at or task.created_at,
                                metadata={"task_id": task.id, "board_id": task.board_id},
                            )
                        )

            # 2. Fetch Cron runs for jobs bound to this project
            cron_jobs_stmt = select(CronJobModel.id, CronJobModel.name).where(CronJobModel.project_id == project_id)
            cron_jobs_rows = (await db.execute(cron_jobs_stmt)).all()
            if cron_jobs_rows:
                job_map = {row[0]: row[1] for row in cron_jobs_rows}
                runs_stmt = (
                    select(CronRunModel)
                    .where(CronRunModel.job_id.in_(list(job_map.keys())))
                    .order_by(desc(CronRunModel.finished_at))
                    .limit(50)
                )
                runs = (await db.execute(runs_stmt)).scalars().all()
                for run in runs:
                    job_name = job_map.get(run.job_id, run.job_id)
                    items.append(
                        ProjectActivityItem(
                            id=f"cron-run-{run.id}",
                            kind="cron_run",
                            title=f"Scheduled task run: {job_name}",
                            detail=f"Status: {run.status}" + (f", duration: {run.duration_ms}ms" if run.duration_ms else ""),
                            actor="scheduler",
                            timestamp=run.finished_at or run.started_at,
                            metadata={"job_id": run.job_id, "status": run.status, "run_id": run.id},
                        )
                    )

            # 3. Fetch Milestones for this project
            milestones_stmt = (
                select(Milestone).where(Milestone.project_id == project_id).order_by(desc(Milestone.created_at)).limit(20)
            )
            milestones = (await db.execute(milestones_stmt)).scalars().all()
            for m in milestones:
                items.append(
                    ProjectActivityItem(
                        id=f"milestone-{m.id}",
                        kind="milestone_created",
                        title=f"Milestone added: {m.title}",
                        detail=m.description or f"Status: {m.status}",
                        actor="system",
                        timestamp=m.created_at,
                        metadata={"milestone_id": m.id, "status": m.status},
                    )
                )

        # Sort all items by timestamp descending
        items.sort(key=lambda x: x.timestamp.replace(tzinfo=UTC) if x.timestamp.tzinfo is None else x.timestamp, reverse=True)

        total = len(items)
        sliced = items[offset : offset + limit]

        return ProjectActivityFeedResponse(
            project_id=project_id,
            items=sliced,
            total=total,
        )
