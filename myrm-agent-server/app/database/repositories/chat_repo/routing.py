"""[INPUT]
- .common (POS: shared constants)

[OUTPUT]
- RoutingMixin

[POS]
ChatRepository mixin: turn routing-tier lookups.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Message

from .common import _answers_of_turn
from .messages import MessagesMixin


def _recorded_routing_tier(extra: object) -> str | None:
    """The `routingTier` string persisted in a message's `extra_data`, None when it holds none."""
    tier = extra.get("routingTier") if isinstance(extra, dict) else None
    return tier if isinstance(tier, str) else None


class RoutingMixin:
    @staticmethod
    async def get_recent_routing_tiers(db: AsyncSession, chat_id: str, limit: int = 5) -> list[str]:
        """Fetch the recorded routing values of the latest assistant messages for momentum calculation.

        Returns the raw `routingTier` strings of the latest *limit* assistant messages that carry `extra_data`, in
        chronological order; messages that recorded no tier add nothing but still occupy the window, so an old routed
        turn does not leak past newer unrouted ones. The column holds either a complexity tier (e.g. "standard",
        "reasoning") or a specialty slot hit (e.g. "code", "long_doc"); callers partition them with
        `services.agent.params.routing_memory.split_recent_routing`.
        """
        result = await db.execute(
            select(Message.extra_data)
            .where(
                Message.chat_id == chat_id,
                Message.role == "assistant",
                Message.extra_data.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        rows: Sequence[object] = result.scalars().all()
        recorded = (_recorded_routing_tier(extra) for extra in reversed(rows))
        return [tier for tier in recorded if tier is not None]

    @staticmethod
    async def get_last_turn_routing_tier(db: AsyncSession, chat_id: str) -> str | None:
        """Raw `routingTier` of the newest answer of the latest user turn that recorded one, None when none did.

        The turn is what a retry replaces, so answers it already deactivated still count. System notices are not
        answers and rows the system appended on its own (auto-continue) carry no tier: both are skipped rather than
        read as an unrouted answer; an earlier turn's tier never stands in for a turn that recorded none.
        """
        last_user = await MessagesMixin.get_last_user_message(db, chat_id)
        if last_user is None:
            return None
        result = await db.execute(
            select(Message.extra_data)
            .where(_answers_of_turn(chat_id, last_user))
            .order_by(Message.created_at.desc(), Message.id.desc())
        )
        rows: Sequence[object] = result.scalars().all()
        return next((tier for tier in map(_recorded_routing_tier, rows) if tier is not None), None)
