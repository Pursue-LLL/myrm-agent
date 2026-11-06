"""[INPUT]
- .common (POS: shared types and helpers)

[OUTPUT]
- BoardsMixin

[POS]
SqlAlchemyKanbanStore mixin: board CRUD and board scope.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.kanban.types import (
    KanbanBoard,
)
from sqlalchemy import select

from app.core.kanban.adapters.sqlalchemy_mapping import (
    apply_board_to_model,
    board_to_domain,
    board_to_model,
)
from app.database.connection import get_session
from app.database.models.kanban import (
    KanbanBoardModel,
)


class BoardsMixin:
    async def get_board(self, board_id: str) -> KanbanBoard | None:
        async with get_session() as session:
            m = await session.get(KanbanBoardModel, board_id)
            return board_to_domain(m) if m else None

    async def list_boards(self, project_id: str | None = None) -> list[KanbanBoard]:
        async with get_session() as session:
            stmt = select(KanbanBoardModel).order_by(KanbanBoardModel.created_at.desc())
            if project_id is not None:
                stmt = stmt.where(KanbanBoardModel.project_id == project_id)
            result = await session.execute(stmt)
            return [board_to_domain(m) for m in result.scalars().all()]

    async def save_board(self, board: KanbanBoard) -> KanbanBoard:
        async with get_session() as session:
            existing = await session.get(KanbanBoardModel, board.board_id)
            if existing:
                apply_board_to_model(board, existing)
                await session.commit()
                await session.refresh(existing)
                return board_to_domain(existing)
            m = board_to_model(board)
            session.add(m)
            await session.commit()
            await session.refresh(m)
            return board_to_domain(m)

    async def set_board_scope(
        self,
        board_id: str,
        *,
        project_id: str | None,
        milestone_id: str | None,
    ) -> None:
        async with get_session() as session:
            board = await session.get(KanbanBoardModel, board_id)
            if board is None:
                raise ValueError(f"Board {board_id} not found")
            board.project_id = project_id
            board.milestone_id = milestone_id
            await session.commit()

    async def delete_board(self, board_id: str) -> bool:
        async with get_session() as session:
            m = await session.get(KanbanBoardModel, board_id)
            if not m:
                return False
            await session.delete(m)
            await session.commit()
            return True
