"""[INPUT]
- .common (POS: shared router and helpers)

[OUTPUT]
- list_groups, update_enabled_groups

[POS]
Channel management API: sender groups.
"""

from __future__ import annotations

import asyncio

from fastapi import Depends
from nanoid import generate as nanoid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.channels.schemas import (
    EnabledGroupsUpdate,
    GroupInfoResponse,
)
from app.database.connection import get_db

from .common import (
    router,
)


@router.get("/groups", response_model=list[GroupInfoResponse])
async def list_groups(
    force_refresh: bool = False,
) -> list[GroupInfoResponse]:
    """List all groups the bot participates in, with enabled status."""
    from app.core.channel_bridge import channel_gateway

    enabled_set = await _load_enabled_groups()
    all_groups = await channel_gateway.list_channel_groups(force_refresh=force_refresh)

    results: list[GroupInfoResponse] = [
        GroupInfoResponse(
            jid=g.jid,
            name=g.name,
            channel=g.channel,
            is_enabled=enabled_set is None or g.jid in enabled_set,
        )
        for g in all_groups
    ]
    results.sort(key=lambda g: g.name.lower())
    return results


@router.put("/groups", status_code=200)
async def update_enabled_groups(
    body: EnabledGroupsUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update the list of enabled groups in the channels config."""
    from app.database.models import UserConfig

    row = (
        await db.execute(
            select(UserConfig).where(
                UserConfig.config_key == "channels",
            )
        )
    ).scalar_one_or_none()

    if row and isinstance(row.config_value, dict):
        config = dict(row.config_value)
    else:
        config = {}

    config["enabledGroups"] = body.enabled_groups
    if row:
        row.config_value = config
    else:
        row = UserConfig(
            id=nanoid(size=16),
            config_key="channels",
            config_value=config,
            version=f"{int(asyncio.get_running_loop().time() * 1000)}_0",
            last_device_id="web",
            is_encrypted=False,
        )
        db.add(row)

    await db.commit()

    from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider

    SqlChannelPolicyProvider._invalidate_cache()

    return {"status": "ok"}


async def _load_enabled_groups() -> set[str] | None:
    """Load enabled groups from the channels config."""

    from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider

    provider = SqlChannelPolicyProvider()
    return await provider.get_enabled_groups()
