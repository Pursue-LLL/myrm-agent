"""
[INPUT] database.models.milestone::Milestone, database.models.project::Project
[OUTPUT] MilestoneService: 里程碑 CRUD 服务
[POS] 里程碑管理服务。提供里程碑增删改查、状态流转和进度统计。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select, update

from app.database.connection import get_session
from app.database.models.kanban import KanbanBoardModel, KanbanTaskModel
from app.database.models.milestone import Milestone
from app.database.models.project import Project

logger = logging.getLogger(__name__)

MILESTONE_STATUSES = ("active", "completed", "archived")


def _milestone_to_dict(m: Milestone) -> dict[str, object]:
    return {
        "id": m.id,
        "projectId": m.project_id,
        "title": m.title,
        "description": m.description,
        "status": m.status,
        "sortOrder": m.sort_order,
        "acceptanceCriteria": m.acceptance_criteria,
        "createdAt": m.created_at.isoformat() if m.created_at else None,
        "updatedAt": m.updated_at.isoformat() if m.updated_at else None,
        "completedAt": m.completed_at.isoformat() if m.completed_at else None,
    }


class MilestoneService:
    """里程碑管理服务"""

    @staticmethod
    async def list_milestones(project_id: str, *, include_archived: bool = False) -> list[dict[str, object]]:
        async with get_session() as db:
            stmt = select(Milestone).where(Milestone.project_id == project_id)
            if not include_archived:
                stmt = stmt.where(Milestone.status != "archived")
            stmt = stmt.order_by(Milestone.sort_order.asc(), Milestone.created_at.asc())
            result = await db.execute(stmt)
            return [_milestone_to_dict(m) for m in result.scalars().all()]

    @staticmethod
    async def get_milestone(milestone_id: str) -> dict[str, object] | None:
        async with get_session() as db:
            stmt = select(Milestone).where(Milestone.id == milestone_id)
            result = await db.execute(stmt)
            m = result.scalar_one_or_none()
            return _milestone_to_dict(m) if m else None

    @staticmethod
    async def create_milestone(
        project_id: str,
        title: str,
        *,
        description: str = "",
        acceptance_criteria: str = "",
    ) -> dict[str, object]:
        async with get_session() as db:
            proj_stmt = select(Project).where(Project.id == project_id)
            proj_result = await db.execute(proj_stmt)
            if not proj_result.scalar_one_or_none():
                raise ValueError(f"Project {project_id} not found")

            count_stmt = select(func.count(Milestone.id)).where(Milestone.project_id == project_id)
            count_result = await db.execute(count_stmt)
            count = count_result.scalar_one()

            milestone = Milestone(
                id=uuid4().hex[:12],
                project_id=project_id,
                title=title.strip(),
                description=description.strip(),
                status="active",
                sort_order=count,
                acceptance_criteria=acceptance_criteria.strip(),
            )
            db.add(milestone)
            await db.commit()
            await db.refresh(milestone)
            return _milestone_to_dict(milestone)

    @staticmethod
    async def update_milestone(
        milestone_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        acceptance_criteria: str | None = None,
        status: str | None = None,
    ) -> dict[str, object] | None:
        async with get_session() as db:
            stmt = select(Milestone).where(Milestone.id == milestone_id)
            result = await db.execute(stmt)
            milestone = result.scalar_one_or_none()
            if not milestone:
                return None

            if title is not None:
                milestone.title = title.strip()
            if description is not None:
                milestone.description = description.strip()
            if acceptance_criteria is not None:
                milestone.acceptance_criteria = acceptance_criteria.strip()
            if status is not None:
                if status not in MILESTONE_STATUSES:
                    raise ValueError(f"Invalid status: {status}. Must be one of {MILESTONE_STATUSES}")
                milestone.status = status
                if status == "completed" and milestone.completed_at is None:
                    milestone.completed_at = datetime.now(timezone.utc)

            await db.commit()
            await db.refresh(milestone)
            return _milestone_to_dict(milestone)

    @staticmethod
    async def delete_milestone(milestone_id: str) -> bool:
        async with get_session() as db:
            stmt = select(Milestone).where(Milestone.id == milestone_id)
            result = await db.execute(stmt)
            milestone = result.scalar_one_or_none()
            if not milestone:
                return False

            # 解绑相关看板
            await db.execute(
                update(KanbanBoardModel)
                .where(KanbanBoardModel.milestone_id == milestone_id)
                .values(milestone_id=None)
            )
            await db.delete(milestone)
            await db.commit()
            return True

    @staticmethod
    async def get_milestone_progress(milestone_id: str) -> dict[str, object] | None:
        """获取里程碑进度：统计关联看板下任务的完成情况"""
        async with get_session() as db:
            stmt = select(Milestone).where(Milestone.id == milestone_id)
            result = await db.execute(stmt)
            milestone = result.scalar_one_or_none()
            if not milestone:
                return None

            boards_stmt = select(KanbanBoardModel.id).where(KanbanBoardModel.milestone_id == milestone_id)
            boards_result = await db.execute(boards_stmt)
            board_ids = [row[0] for row in boards_result.all()]

            if not board_ids:
                return {"milestoneId": milestone_id, "totalTasks": 0, "completedTasks": 0, "progress": 0.0}

            total_stmt = select(func.count(KanbanTaskModel.id)).where(KanbanTaskModel.board_id.in_(board_ids))
            total_result = await db.execute(total_stmt)
            total = total_result.scalar_one()

            done_stmt = (
                select(func.count(KanbanTaskModel.id))
                .where(KanbanTaskModel.board_id.in_(board_ids))
                .where(KanbanTaskModel.status == "done")
            )
            done_result = await db.execute(done_stmt)
            done = done_result.scalar_one()

            progress = (done / total * 100) if total > 0 else 0.0
            return {
                "milestoneId": milestone_id,
                "totalTasks": total,
                "completedTasks": done,
                "progress": round(progress, 1),
            }

    @staticmethod
    async def get_project_roadmap_summary(project_id: str) -> dict[str, object]:
        """生成项目路线图摘要，用于 Agent context injection"""
        async with get_session() as db:
            proj_stmt = select(Project).where(Project.id == project_id)
            proj_result = await db.execute(proj_stmt)
            project = proj_result.scalar_one_or_none()
            if not project:
                return {}

            milestones_stmt = (
                select(Milestone)
                .where(Milestone.project_id == project_id, Milestone.status != "archived")
                .order_by(Milestone.sort_order.asc())
            )
            milestones_result = await db.execute(milestones_stmt)
            milestones = milestones_result.scalars().all()

            summary_parts: list[str] = []
            if project.description:
                summary_parts.append(f"Project: {project.name} — {project.description}")
            else:
                summary_parts.append(f"Project: {project.name}")

            if project.goal_summary:
                summary_parts.append(f"Current Focus: {project.goal_summary}")

            active_milestones: list[dict[str, object]] = []
            completed_milestones: list[dict[str, object]] = []

            for ms in milestones:
                ms_dict = _milestone_to_dict(ms)
                if ms.status == "completed":
                    completed_milestones.append(ms_dict)
                else:
                    active_milestones.append(ms_dict)

            return {
                "projectName": project.name,
                "projectDescription": project.description,
                "goalSummary": project.goal_summary,
                "activeMilestones": active_milestones,
                "completedMilestones": completed_milestones,
                "contextSnippet": "\n".join(summary_parts),
            }
