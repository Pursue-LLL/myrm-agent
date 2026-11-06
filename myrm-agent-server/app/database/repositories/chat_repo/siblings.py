"""[INPUT]
- .common (POS: shared constants)

[OUTPUT]
- SiblingsMixin

[POS]
ChatRepository mixin: assistant sibling selection, counting and detail projection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.models import Message

from .common import _answers_of_turn


@dataclass
class _SiblingGroupInfo:
    total: int
    ids: list[str] = field(default_factory=list)


class SiblingDetail(TypedDict):
    id: str
    is_active: bool
    created_at: datetime


class SiblingsMixin:
    @staticmethod
    async def _batch_sibling_counts(
        db: AsyncSession,
        group_ids: set[str],
    ) -> dict[str, _SiblingGroupInfo]:
        """Batch-fetch sibling counts and ordered ids for multiple groups."""
        result = await db.execute(
            select(Message.sibling_group_id, Message.id, Message.created_at)
            .where(Message.sibling_group_id.in_(group_ids))
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        groups: dict[str, _SiblingGroupInfo] = {}
        for row in result.all():
            gid = row.sibling_group_id
            if gid not in groups:
                groups[gid] = _SiblingGroupInfo(total=0, ids=[])
            groups[gid].total += 1
            groups[gid].ids.append(row.id)
        return groups

    @staticmethod
    async def deactivate_last_assistant_siblings(
        db: AsyncSession,
        chat_id: str,
        last_user_msg: MessageDTO,
    ) -> tuple[str, str]:
        """Mark the last assistant messages as inactive and return (query, sibling_group_id).

        Finds all assistant messages after the given user message, assigns them
        a shared sibling_group_id (reusing existing if present), and sets
        is_active=False.  Returns the user query and the sibling_group_id so
        the caller can attach the same group to the regenerated response.
        """
        result = await db.execute(select(Message).where(_answers_of_turn(chat_id, last_user_msg)))
        assistant_msgs = result.scalars().all()

        group_id = ""
        for m in assistant_msgs:
            if m.sibling_group_id:
                group_id = m.sibling_group_id
                break
        if not group_id:
            group_id = str(uuid4())

        for m in assistant_msgs:
            m.is_active = False
            m.sibling_group_id = group_id

        return last_user_msg.content, group_id

    @staticmethod
    async def switch_active_sibling(
        db: AsyncSession,
        sibling_group_id: str,
        target_message_id: str,
    ) -> bool:
        """Set the target message as active and all other siblings as inactive."""
        result = await db.execute(select(Message).where(Message.sibling_group_id == sibling_group_id))
        siblings = result.scalars().all()
        if not siblings:
            return False

        found = False
        for m in siblings:
            if m.id == target_message_id:
                m.is_active = True
                found = True
            else:
                m.is_active = False
        return found

    @staticmethod
    async def get_sibling_info(
        db: AsyncSession,
        sibling_group_id: str,
    ) -> list[SiblingDetail]:
        """Return ordered list of sibling message summaries for a group."""
        result = await db.execute(
            select(Message.id, Message.is_active, Message.created_at)
            .where(Message.sibling_group_id == sibling_group_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return [SiblingDetail(id=row.id, is_active=row.is_active, created_at=row.created_at) for row in result.all()]
