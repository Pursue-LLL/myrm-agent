"""Turn 生命周期管理

管理 Turn 的创建、状态转换和查询。
仅在本地模式下启用。
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.deploy_mode import is_local_mode
from app.database.models import AgentEvent, AgentTurn
from app.services.event.recorder import EventRecorder
from app.services.event.types import EventCallback, TurnStatus


class TurnManager:
    """Turn 管理器

    管理 Turn 的生命周期：创建、开始、完成、错误、取消
    """

    def __init__(self, session: AsyncSession):
        self._session = session
        self._enabled = is_local_mode()

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def create_turn(
        self,
        chat_id: str,
        user_input: str | None = None,
        callback: EventCallback | None = None,
    ) -> tuple[AgentTurn | None, EventRecorder | None]:
        """创建新的 Turn

        Returns:
            (AgentTurn, EventRecorder) 元组（如果启用），否则返回 (None, None)
        """
        if not self._enabled:
            return None, None

        result = await self._session.execute(select(AgentTurn).where(AgentTurn.chat_id == chat_id))
        turn_count = len(result.scalars().all())

        turn = AgentTurn(
            id=str(uuid.uuid4()),
            chat_id=chat_id,
            turn_index=turn_count,
            user_input=user_input,
            status=TurnStatus.PENDING.value,
        )
        self._session.add(turn)
        await self._session.flush()

        recorder = EventRecorder(self._session, turn.id, callback)
        return turn, recorder

    async def start_turn(self, turn_id: str) -> None:
        """开始 Turn"""
        if not self._enabled:
            return

        await self._session.execute(
            update(AgentTurn)
            .where(AgentTurn.id == turn_id)
            .values(
                status=TurnStatus.RUNNING.value,
                started_at=datetime.now(timezone.utc),
            )
        )

    async def complete_turn(self, turn_id: str) -> None:
        """完成 Turn"""
        if not self._enabled:
            return

        result = await self._session.execute(select(AgentTurn.started_at).where(AgentTurn.id == turn_id))
        started_at = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        duration_ms = None
        if started_at:
            duration_ms = int((now - started_at).total_seconds() * 1000)

        await self._session.execute(
            update(AgentTurn)
            .where(AgentTurn.id == turn_id)
            .values(
                status=TurnStatus.COMPLETED.value,
                completed_at=now,
                duration_ms=duration_ms,
            )
        )

    async def error_turn(self, turn_id: str) -> None:
        """Turn 发生错误"""
        if not self._enabled:
            return

        result = await self._session.execute(select(AgentTurn.started_at).where(AgentTurn.id == turn_id))
        started_at = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        duration_ms = None
        if started_at:
            duration_ms = int((now - started_at).total_seconds() * 1000)

        await self._session.execute(
            update(AgentTurn)
            .where(AgentTurn.id == turn_id)
            .values(
                status=TurnStatus.ERROR.value,
                completed_at=now,
                duration_ms=duration_ms,
            )
        )

    async def cancel_turn(self, turn_id: str) -> None:
        """取消 Turn"""
        if not self._enabled:
            return

        await self._session.execute(
            update(AgentTurn)
            .where(AgentTurn.id == turn_id)
            .values(
                status=TurnStatus.CANCELLED.value,
                completed_at=datetime.now(timezone.utc),
            )
        )

    async def get_turn(self, turn_id: str) -> AgentTurn | None:
        """获取 Turn"""
        if not self._enabled:
            return None

        result = await self._session.execute(select(AgentTurn).where(AgentTurn.id == turn_id))
        return result.scalar_one_or_none()

    async def get_turns_by_chat(self, chat_id: str, limit: int = 50, offset: int = 0) -> list[AgentTurn]:
        """获取 Chat 的所有 Turn"""
        if not self._enabled:
            return []

        result = await self._session.execute(
            select(AgentTurn)
            .where(AgentTurn.chat_id == chat_id)
            .order_by(AgentTurn.turn_index.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_events_by_turn(self, turn_id: str, limit: int = 100, offset: int = 0) -> list[AgentEvent]:
        """获取 Turn 的所有 Event"""
        if not self._enabled:
            return []

        result = await self._session.execute(
            select(AgentEvent)
            .where(AgentEvent.turn_id == turn_id)
            .order_by(AgentEvent.event_index.asc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
