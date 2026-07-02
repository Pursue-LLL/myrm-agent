"""
[INPUT] database.models.project::Project, database.models.chat::Chat
[OUTPUT] ProjectService: 项目 CRUD 服务
[POS] 项目管理服务。提供项目的增删改查和会话归属管理。
"""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import delete, func, select, update

from app.database.connection import get_session
from app.database.models.chat import Chat
from app.database.models.project import Project

logger = logging.getLogger(__name__)

PROJECT_COLORS = [
    "#7cb9ff",
    "#ff7eb3",
    "#7afcb4",
    "#ffd97c",
    "#c4b5fd",
    "#fb923c",
    "#67e8f9",
    "#f87171",
    "#a3e635",
    "#e879f9",
]


def _project_to_dict(p: Project) -> dict[str, object]:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "color": p.color,
        "sortOrder": p.sort_order,
        "workspacePath": p.workspace_path,
        "goalSummary": p.goal_summary,
        "createdAt": p.created_at.isoformat() if p.created_at else None,
        "updatedAt": p.updated_at.isoformat() if p.updated_at else None,
    }


class ProjectService:
    """项目管理服务"""

    @staticmethod
    async def get_project(project_id: str) -> Project | None:
        async with get_session() as db:
            stmt = select(Project).where(Project.id == project_id)
            result = await db.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    async def list_projects() -> list[dict[str, object]]:
        async with get_session() as db:
            stmt = select(Project).order_by(Project.sort_order.asc(), Project.created_at.asc())
            result = await db.execute(stmt)
            projects = result.scalars().all()
            return [_project_to_dict(p) for p in projects]

    @staticmethod
    async def create_project(name: str, color: str | None = None, description: str = "") -> dict[str, object]:
        async with get_session() as db:
            count_stmt = select(func.count(Project.id))
            count_result = await db.execute(count_stmt)
            count = count_result.scalar_one()

            project_id = uuid4().hex[:12]
            workspace_path = f"/persistent/workspace/project_{project_id}"

            project = Project(
                id=project_id,
                name=name.strip(),
                description=description.strip(),
                color=color or PROJECT_COLORS[count % len(PROJECT_COLORS)],
                sort_order=count,
                workspace_path=workspace_path,
            )
            db.add(project)

            from app.services.memory.shared_context import SharedContextService

            shared_context_svc = SharedContextService(db)
            context = await shared_context_svc.create_context(
                name=f"Project: {project.name}", description=f"Shared memory context for project {project.name}"
            )
            await shared_context_svc.bind_context(context_id=context.id, target_type="project", target_id=project.id)

            await db.commit()
            await db.refresh(project)
            return _project_to_dict(project)

    @staticmethod
    async def update_project(
        project_id: str,
        name: str | None = None,
        color: str | None = None,
        workspace_path: str | None = None,
        description: str | None = None,
        goal_summary: str | None = None,
    ) -> dict[str, object] | None:
        async with get_session() as db:
            stmt = select(Project).where(Project.id == project_id)
            result = await db.execute(stmt)
            project = result.scalar_one_or_none()
            if not project:
                return None

            if name is not None:
                project.name = name.strip()
            if color is not None:
                project.color = color
            if workspace_path is not None:
                project.workspace_path = workspace_path
            if description is not None:
                project.description = description.strip()
            if goal_summary is not None:
                project.goal_summary = goal_summary.strip()

            await db.commit()
            await db.refresh(project)
            return _project_to_dict(project)

    @staticmethod
    async def delete_project(project_id: str) -> bool:
        """Delete a project and unassign all its chats (chats are NOT deleted)."""
        async with get_session() as db:
            stmt = select(Project).where(Project.id == project_id)
            result = await db.execute(stmt)
            project = result.scalar_one_or_none()
            if not project:
                return False

            await db.execute(update(Chat).where(Chat.project_id == project_id).values(project_id=None))
            await db.execute(delete(Project).where(Project.id == project_id))
            await db.commit()
            return True

    @staticmethod
    async def move_chat_to_project(chat_id: str, project_id: str | None) -> bool:
        async with get_session() as db:
            stmt = select(Chat).where(Chat.id == chat_id, Chat.deleted_at.is_(None))
            result = await db.execute(stmt)
            chat = result.scalar_one_or_none()
            if not chat:
                return False

            if project_id:
                proj_stmt = select(Project).where(Project.id == project_id)
                proj_result = await db.execute(proj_stmt)
                if not proj_result.scalar_one_or_none():
                    return False

            chat.project_id = project_id
            await db.commit()
            return True

    @staticmethod
    async def batch_move_chats(chat_ids: list[str], project_id: str | None) -> int:
        """Batch move multiple chats to a project (or unassign with project_id=None)."""
        if not chat_ids:
            return 0

        async with get_session() as db:
            if project_id:
                proj_stmt = select(Project).where(Project.id == project_id)
                proj_result = await db.execute(proj_stmt)
                if not proj_result.scalar_one_or_none():
                    return 0

            stmt = update(Chat).where(Chat.id.in_(chat_ids), Chat.deleted_at.is_(None)).values(project_id=project_id)
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount  # type: ignore[return-value]
