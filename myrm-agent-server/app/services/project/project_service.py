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
    "#7cb9ff", "#ff7eb3", "#7afcb4", "#ffd97c", "#c4b5fd",
    "#fb923c", "#67e8f9", "#f87171", "#a3e635", "#e879f9",
]


class ProjectService:
    """项目管理服务"""

    @staticmethod
    async def list_projects() -> list[dict[str, object]]:
        async with get_session() as db:
            stmt = select(Project).order_by(Project.sort_order.asc(), Project.created_at.asc())
            result = await db.execute(stmt)
            projects = result.scalars().all()
            return [
                {
                    "id": p.id,
                    "name": p.name,
                    "color": p.color,
                    "sortOrder": p.sort_order,
                    "createdAt": p.created_at.isoformat() if p.created_at else None,
                    "updatedAt": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in projects
            ]

    @staticmethod
    async def create_project(name: str, color: str | None = None) -> dict[str, object]:
        async with get_session() as db:
            count_stmt = select(func.count(Project.id))
            count_result = await db.execute(count_stmt)
            count = count_result.scalar_one()

            project = Project(
                id=uuid4().hex[:12],
                name=name.strip(),
                color=color or PROJECT_COLORS[count % len(PROJECT_COLORS)],
                sort_order=count,
            )
            db.add(project)
            await db.commit()
            await db.refresh(project)
            return {
                "id": project.id,
                "name": project.name,
                "color": project.color,
                "sortOrder": project.sort_order,
                "createdAt": project.created_at.isoformat() if project.created_at else None,
                "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
            }

    @staticmethod
    async def update_project(project_id: str, name: str | None = None, color: str | None = None) -> dict[str, object] | None:
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

            await db.commit()
            await db.refresh(project)
            return {
                "id": project.id,
                "name": project.name,
                "color": project.color,
                "sortOrder": project.sort_order,
                "createdAt": project.created_at.isoformat() if project.created_at else None,
                "updatedAt": project.updated_at.isoformat() if project.updated_at else None,
            }

    @staticmethod
    async def delete_project(project_id: str) -> bool:
        """Delete a project and unassign all its chats (chats are NOT deleted)."""
        async with get_session() as db:
            stmt = select(Project).where(Project.id == project_id)
            result = await db.execute(stmt)
            project = result.scalar_one_or_none()
            if not project:
                return False

            await db.execute(
                update(Chat).where(Chat.project_id == project_id).values(project_id=None)
            )
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

            stmt = (
                update(Chat)
                .where(Chat.id.in_(chat_ids), Chat.deleted_at.is_(None))
                .values(project_id=project_id)
            )
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount  # type: ignore[return-value]
