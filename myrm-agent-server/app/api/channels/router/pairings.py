"""[INPUT]
- .common (POS: shared router and helpers)

[OUTPUT]
- list_pairings, create_pairing, delete_pairing, update_pairing_status

[POS]
Channel management API: pairing CRUD and status updates.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import Depends, HTTPException
from nanoid import generate as nanoid
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.channels.schemas import (
    PairingCreate,
    PairingResponse,
    PairingStatusUpdate,
)
from app.database.connection import get_db
from app.database.models import ChannelPairingModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository

from .common import (
    router,
)


@router.get("/pairings", response_model=list[PairingResponse])
async def list_pairings(
    db: AsyncSession = Depends(get_db),
) -> list[PairingResponse]:
    """List all channel pairings for the current user."""
    rows = (await db.execute(select(ChannelPairingModel).order_by(ChannelPairingModel.created_at.desc()))).scalars().all()

    pairings: list[PairingResponse] = []
    for r in rows:
        today_usage = await ChannelMessageRepository.get_daily_trigger_count(db, r.channel, r.sender_id)
        pairings.append(
            PairingResponse(
                id=r.id,
                channel=r.channel,
                sender_id=r.sender_id,
                user_id="sandbox" if getattr(r, "role", "member") == "admin" else f"paired_member_{r.channel}_{r.sender_id}",
                status=r.status,
                display_name=r.display_name,
                role=getattr(r, "role", "member") or "member",
                daily_quota=getattr(r, "daily_quota", None),
                today_usage=today_usage,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return pairings


@router.post("/pairings", response_model=PairingResponse, status_code=201)
async def create_pairing(
    body: PairingCreate,
    db: AsyncSession = Depends(get_db),
) -> PairingResponse:
    """Bind an external channel identity to the current user."""
    sender_id = _normalize_sender_id(body.channel, body.sender_id)
    existing = (
        await db.execute(
            select(ChannelPairingModel).where(
                ChannelPairingModel.channel == body.channel,
                ChannelPairingModel.sender_id == sender_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        today_usage = await ChannelMessageRepository.get_daily_trigger_count(db, existing.channel, existing.sender_id)
        return PairingResponse(
            id=existing.id,
            channel=existing.channel,
            sender_id=existing.sender_id,
            user_id="sandbox"
            if getattr(existing, "role", "member") == "admin"
            else f"paired_member_{existing.channel}_{existing.sender_id}",
            status=existing.status,
            display_name=existing.display_name,
            role=getattr(existing, "role", "member") or "member",
            daily_quota=getattr(existing, "daily_quota", None),
            today_usage=today_usage,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )

    row = ChannelPairingModel(
        id=nanoid(size=16),
        channel=body.channel,
        sender_id=sender_id,
        status="active",
        role=body.role,
        daily_quota=body.daily_quota,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    today_usage = await ChannelMessageRepository.get_daily_trigger_count(db, row.channel, row.sender_id)
    return PairingResponse(
        id=row.id,
        channel=row.channel,
        sender_id=row.sender_id,
        user_id="sandbox" if row.role == "admin" else f"paired_member_{row.channel}_{row.sender_id}",
        status=row.status,
        display_name=row.display_name,
        role=row.role,
        daily_quota=row.daily_quota,
        today_usage=today_usage,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/pairings/{pairing_id}", status_code=204)
async def delete_pairing(
    pairing_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a channel pairing."""
    result = await db.execute(delete(ChannelPairingModel).where(ChannelPairingModel.id == pairing_id))
    rowcount = getattr(result, "rowcount", None)
    deleted = int(rowcount) if isinstance(rowcount, int) else 0
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Pairing not found")
    await db.commit()


@router.patch("/pairings/{pairing_id}", response_model=PairingResponse)
async def update_pairing_status(
    pairing_id: str,
    body: PairingStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> PairingResponse:
    """Update the status, role, daily_quota and/or display_name of a channel pairing."""
    if body.status is None and body.display_name is None and body.role is None and body.daily_quota is None:
        raise HTTPException(status_code=422, detail="Nothing to update")

    row = (await db.execute(select(ChannelPairingModel).where(ChannelPairingModel.id == pairing_id))).scalar_one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Pairing not found")

    was_pending = row.status == "pending"
    if body.status is not None:
        row.status = body.status
    if body.display_name is not None:
        row.display_name = body.display_name
    if body.role is not None:
        row.role = body.role
    if body.daily_quota is not None:
        row.daily_quota = body.daily_quota
    await db.commit()
    await db.refresh(row)

    if was_pending and body.status == "active":
        await _notify_pairing_approved(row.channel, row.sender_id)

    today_usage = await ChannelMessageRepository.get_daily_trigger_count(db, row.channel, row.sender_id)
    return PairingResponse(
        id=row.id,
        channel=row.channel,
        sender_id=row.sender_id,
        user_id="sandbox" if row.role == "admin" else f"paired_member_{row.channel}_{row.sender_id}",
        status=row.status,
        display_name=row.display_name,
        role=row.role,
        daily_quota=row.daily_quota,
        today_usage=today_usage,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_sender_id(channel: str, sender_id: str) -> str:
    """Normalize and validate sender_id for a given channel."""
    if channel != "whatsapp":
        return sender_id
    if "@" in sender_id:
        return sender_id
    digits = "".join(c for c in sender_id if c.isdigit())
    if len(digits) < 7 or len(digits) > 15:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid phone number: expected 7-15 digits, got {len(digits)}",
        )
    return f"{digits}@s.whatsapp.net"


async def _notify_pairing_approved(channel: str, sender_id: str) -> None:
    """Best-effort send approval notification to the sender via their IM channel."""
    try:
        from app.channels.types import OutboundMessage
        from app.core.channel_bridge import channel_gateway

        msg = OutboundMessage(
            channel=channel,
            recipient_id=sender_id,
            content="✅ 您的访问已获批准，现在可以发送消息了。\nYour access has been approved. You can now send messages.",
            user_id="",
        )
        asyncio.create_task(channel_gateway.bus.publish_outbound(msg))
    except Exception:
        logging.getLogger(__name__).debug("Failed to send approval notification", exc_info=True)
