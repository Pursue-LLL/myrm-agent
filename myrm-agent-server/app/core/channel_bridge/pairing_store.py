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

from app.channels.protocols.pairing import PairingRole, PairingStatus

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

            if not row:
                return None
            role_val = getattr(row, "role", "member") or "member"
            if role_val == PairingRole.ADMIN:
                return "sandbox"
            return f"paired_member_{channel}_{sender_id}"

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
        role: PairingRole = PairingRole.MEMBER,
        daily_quota: int | None = None,
    ) -> None:
        import asyncio

        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from sqlalchemy.exc import OperationalError

        from app.database.connection import get_session
        from app.database.models import ChannelPairingModel

        role_str = role.value if hasattr(role, "value") else str(role)
        status_str = status.value if hasattr(status, "value") else str(status)

        update_set: dict[str, object] = {
            "status": status_str,
            "role": role_str,
        }
        if display_name is not None:
            update_set["display_name"] = display_name
        if daily_quota is not None:
            update_set["daily_quota"] = daily_quota

        stmt = (
            sqlite_insert(ChannelPairingModel)
            .values(
                id=nanoid(size=16),
                channel=channel,
                sender_id=sender_id,
                status=status_str,
                display_name=display_name,
                role=role_str,
                daily_quota=daily_quota,
            )
            .on_conflict_do_update(
                index_elements=["channel", "sender_id"],
                set_=update_set,
            )
        )

        for attempt in range(5):
            try:
                async with get_session() as session:
                    await session.execute(stmt)
                    await session.commit()
                break
            except OperationalError as exc:
                if "database is locked" in str(exc) and attempt < 4:
                    await asyncio.sleep(0.02 * (attempt + 1))
                    continue
                raise

        logger.warning(
            "Pairing bound: %s/%s (status=%s, role=%s, quota=%s)",
            channel,
            sender_id,
            status_str,
            role_str,
            daily_quota,
        )

        if status_str == PairingStatus.PENDING:
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
        detail = await self.get_pairing_detail(channel, sender_id)
        return detail[0] if detail else None

    async def get_pairing_detail(
        self, channel: str, sender_id: str
    ) -> tuple[PairingStatus, PairingRole, int | None] | None:
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
            status_val = PairingStatus(row.status)
            role_val = PairingRole(getattr(row, "role", "member") or "member")
            quota_val = getattr(row, "daily_quota", None)
            return status_val, role_val, quota_val
