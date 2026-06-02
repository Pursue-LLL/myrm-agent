"""ChannelStatusProvider implementation for /status command.

[INPUT]
- app.channels.protocols.status::StatusProvider, SessionStatus
- app.database.connection::get_session
- app.database.models.chat::Chat
- app.database.models.agent::Agent

[OUTPUT]
- ChannelStatusProvider: Business-layer StatusProvider implementation

[POS]
Maps the framework-level StatusProvider protocol to the application's Chat
database, returning session metadata (id, title, token usage, model,
created_at, last_activity) for the /status slash command in channels.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from app.channels.protocols.status import SessionStatus
from app.database.connection import get_session
from app.database.models.chat import Chat

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class ChannelStatusProvider:
    """Business-layer StatusProvider for /status command.

    Queries the most recently updated Chat matching the channel+peer
    combination and returns session metadata.

    channel_session_key format: ``{channel}:{peer_kind}:{peer_id}[:thread:...][:agent:...]``
    Match either exact tail (peer_id is the final segment) or peer_id
    followed by a colon (thread/agent suffix exists). This avoids partial
    ID collisions while supporting all key variants.
    """

    async def get_session_status(self, channel: str, peer_id: str) -> SessionStatus | None:
        """Look up the active channel session and return its metadata."""
        prefix = f"{channel}:%:"
        exact_tail = f"{prefix}{peer_id}"
        with_suffix = f"{prefix}{peer_id}:%"

        async with get_session() as db:
            stmt = (
                select(Chat)
                .where(
                    Chat.channel_session_key.isnot(None),
                    or_(
                        Chat.channel_session_key.like(exact_tail),
                        Chat.channel_session_key.like(with_suffix),
                    ),
                )
                .order_by(Chat.updated_at.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            chat = result.scalar_one_or_none()

            if not chat:
                return None

            model_name = await self._resolve_model_name(db, chat.agent_id)

            created_str = chat.created_at.strftime("%Y-%m-%d %H:%M") if chat.created_at else None
            activity_str = chat.updated_at.strftime("%Y-%m-%d %H:%M") if chat.updated_at else None

            return SessionStatus(
                session_id=chat.id,
                title=chat.title,
                total_tokens=chat.total_tokens,
                model_name=model_name,
                created_at=created_str,
                last_activity=activity_str,
            )

    @staticmethod
    async def _resolve_model_name(
        db: "AsyncSession", agent_id: str | None
    ) -> str | None:
        """Resolve model name from agent's model_selection config.

        Reuses the existing DB session to avoid an extra connection.
        """
        if not agent_id:
            return None
        try:
            from app.database.models import Agent

            agent = (
                await db.execute(select(Agent).where(Agent.id == agent_id))
            ).scalar_one_or_none()
            if not agent or not agent.model_selection:
                return None
            return agent.model_selection.get("model") or agent.model_selection.get("modelId")
        except Exception:
            return None
