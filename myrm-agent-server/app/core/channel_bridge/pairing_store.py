"""SQLAlchemy-backed PairingStore implementation.

Implements the framework-level PairingStore protocol using the
application's database models and session management.

[INPUT]
- app.channels.protocols::PairingStore, PairingStatus
- database.models::ChannelPairingModel
- database.connection::get_session

[OUTPUT]
- SqlPairingStore: PairingStore 的 SQLAlchemy 实现

[POS]
业务层的用户身份绑定存储。将框架层的 PairingStore 协议映射到
SQLAlchemy ORM 操作，通过 channel_pairings 表持久化绑定关系。
"""

from __future__ import annotations

import logging

from nanoid import generate as nanoid
from sqlalchemy import select

from app.channels.protocols.pairing import PairingStatus

logger = logging.getLogger(__name__)


class SqlPairingStore:
    """PairingStore backed by SQLAlchemy + channel_pairings table."""

    async def resolve(self, channel: str, sender_id: str) -> str | None:
        from app.database.connection import get_session
        from app.database.models import ChannelPairingModel

        async with get_session() as session:
            row = (
                await session.execute(
                    select(ChannelPairingModel).where(
                        ChannelPairingModel.channel == channel,
                        ChannelPairingModel.sender_id == sender_id,
                        ChannelPairingModel.status == PairingStatus.ACTIVE,
                    )
                )
            ).scalar_one_or_none()

            return "sandbox" if row else None

    async def touch_display_name(self, channel: str, sender_id: str, display_name: str) -> None:
        from sqlalchemy import or_, update

        from app.database.connection import get_session
        from app.database.models import ChannelPairingModel

        async with get_session() as session:
            await session.execute(
                update(ChannelPairingModel)
                .where(
                    ChannelPairingModel.channel == channel,
                    ChannelPairingModel.sender_id == sender_id,
                    or_(
                        ChannelPairingModel.display_name.is_(None),
                        ChannelPairingModel.display_name != display_name,
                    ),
                )
                .values(display_name=display_name)
            )
            await session.commit()

    async def bind(
        self,
        channel: str,
        sender_id: str,
        user_id: str = "",
        *,
        status: PairingStatus = PairingStatus.ACTIVE,
        display_name: str | None = None,
    ) -> None:
        from sqlalchemy import update

        from app.database.connection import get_session
        from app.database.models import ChannelPairingModel

        is_new = False
        async with get_session() as session:
            existing = (
                await session.execute(
                    select(ChannelPairingModel).where(
                        ChannelPairingModel.channel == channel,
                        ChannelPairingModel.sender_id == sender_id,
                    )
                )
            ).scalar_one_or_none()

            if existing:
                values: dict[str, str | None] = {"status": status}
                if display_name:
                    values["display_name"] = display_name
                await session.execute(update(ChannelPairingModel).where(ChannelPairingModel.id == existing.id).values(**values))
            else:
                is_new = True
                session.add(
                    ChannelPairingModel(
                        id=nanoid(size=16),
                        channel=channel,
                        sender_id=sender_id,
                        status=status,
                        display_name=display_name,
                    )
                )
            await session.commit()

        logger.warning("Pairing bound: %s/%s  (status=%s)", channel, sender_id, status)

        if status == PairingStatus.PENDING and is_new:
            self._emit_pending_event(channel, sender_id, display_name)

    @staticmethod
    def _emit_pending_event(channel: str, sender_id: str, display_name: str | None = None) -> None:
        """Best-effort publish to ServerEventBus when a new pending pairing is created."""
        try:
            from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

            data: dict[str, str] = {"channel": channel, "sender_id": sender_id}
            if display_name:
                data["display_name"] = display_name
            get_event_bus().publish(AppEvent(event_type=AppEventType.PAIRING_PENDING, data=data))
        except Exception as exc:
            logger.warning("Failed to emit pairing_pending event: %s", exc)

    async def unbind(self, channel: str, sender_id: str) -> None:
        from sqlalchemy import delete

        from app.database.connection import get_session
        from app.database.models import ChannelPairingModel

        async with get_session() as session:
            await session.execute(
                delete(ChannelPairingModel).where(
                    ChannelPairingModel.channel == channel,
                    ChannelPairingModel.sender_id == sender_id,
                )
            )
            await session.commit()

    async def get_status(self, channel: str, sender_id: str) -> PairingStatus | None:
        from app.database.connection import get_session
        from app.database.models import ChannelPairingModel

        async with get_session() as session:
            row = (
                await session.execute(
                    select(ChannelPairingModel).where(
                        ChannelPairingModel.channel == channel,
                        ChannelPairingModel.sender_id == sender_id,
                    )
                )
            ).scalar_one_or_none()

            if not row:
                return None
            return PairingStatus(row.status)
