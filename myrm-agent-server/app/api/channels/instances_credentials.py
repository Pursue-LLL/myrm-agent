"""Channel instance credentials and configuration endpoints.

[INPUT]
- api.channels.router::channel_credentials_key (POS: Channel 管理路由层)
- database.connection::get_db (POS: 数据库连接管理)
- database.models::UserConfig (POS: ORM 模型)

[OUTPUT]
- router: 频道实例凭证存取 + 配置管理端点

[POS]
频道实例凭证与配置管理端点（与 `instances.py` 的 CRUD 分离，控制单文件行数）。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends
from nanoid import generate as nanoid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.channels.router import channel_credentials_key
from app.database.connection import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{channel_name}/credentials")
async def get_channel_credentials(
    channel_name: str,
) -> dict[str, str]:
    """Get channel credentials (with sensitive fields redacted).

    Boolean values are normalized to lowercase strings (``"true"/"false"``)
    so the frontend ``useLark === 'true'`` comparison stays stable.
    """
    from app.services.config.service import ConfigService

    config_key = channel_credentials_key(channel_name)
    record = await ConfigService().get(config_key)

    if record is None:
        return {}

    credentials = {
        str(k): (str(v).lower() if isinstance(v, bool) else v)
        for k, v in record.value.items()
    }

    for key, value in credentials.items():
        if isinstance(value, str) and any(
            sensitive in key.lower() for sensitive in ["token", "password", "secret", "key"]
        ):
            if len(value) > 4:
                credentials[key] = "•" * (len(value) - 4) + value[-4:]
            else:
                credentials[key] = "•" * len(value)

    return credentials


@router.post("/{channel_name}/credentials", status_code=201)
async def save_channel_credentials(
    channel_name: str,
    credentials: dict[str, str],
) -> dict[str, str]:
    """Save channel credentials to the database (encrypted) and hot-reload.

    Only the submitted fields are overwritten; credentials omitted from the
    request (e.g. ``verificationToken`` when only rotating ``appSecret``) are
    kept.
    When the channel is currently registered in the gateway, it is rebuilt
    from the merged credentials with the same instance id so that agent
    bindings and the channel name are preserved, then atomically swapped in
    via ``ChannelGateway.swap_channel`` (the previous instance is restored if
    the swap fails). When it is not registered, a hot-register attempt is made
    so the update takes effect immediately; if hot-reload fails, the update
    takes effect on the next startup.
    """
    from app.services.config.service import ConfigService

    config_key = channel_credentials_key(channel_name)
    record = await ConfigService().get(config_key)
    merged = dict(record.value) if record else {}
    merged.update(credentials)
    await ConfigService().set(config_key, merged, device_id="web")

    from app.core.channel_bridge import channel_gateway

    try:
        ch = channel_gateway.bus.get_channel(channel_name)
        if ch is None:
            from app.api.config.router import _try_hot_register_channel

            await _try_hot_register_channel(config_key)
            return {"status": "saved", "message": "Credentials saved successfully"}

        base_type = channel_gateway._resolve_channel_type(ch)
        if channel_name == base_type:
            from app.api.config.router import _try_hot_register_channel

            await _try_hot_register_channel(config_key)
            return {"status": "saved", "message": "Credentials saved successfully"}

        from app.core.channel_bridge.channel_factory import (
            create_channel_instance as factory_create,
        )

        # Build the replacement first so a construction failure (e.g. invalid
        # credentials) leaves the current channel untouched instead of removing
        # it and then failing to re-add it. The gateway's atomic swap keeps the
        # old instance alive until the replacement registers, restoring it on
        # failure so a bad swap never leaves the instance silently offline.
        new_channel = await factory_create(
            channel_type=base_type,
            instance_id=ch.instance_id or channel_name,
            credentials=merged,
        )
        new_channel.display_name = ch.display_name
        await channel_gateway.swap_channel(new_channel, ch)
        logger.info("Channel '%s' re-registered with updated credentials", channel_name)
    except Exception as exc:
        logger.warning(
            "Failed to hot-reload channel '%s' after credential update: %s",
            channel_name,
            exc,
        )

    return {"status": "saved", "message": "Credentials saved successfully"}


@router.get("/{channel_name}/config", status_code=200)
async def get_channel_config(
    channel_name: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Get channel configuration (permission control, session settings, etc.)."""
    from app.database.models import UserConfig

    row = (
        await db.execute(
            select(UserConfig).where(
                UserConfig.config_key == "channels",
            )
        )
    ).scalar_one_or_none()

    if not row or not isinstance(row.config_value, dict):
        return {}

    config = row.config_value
    channel_config = config.get("channels", {}).get(channel_name, {})
    return dict(channel_config) if isinstance(channel_config, dict) else {}


@router.patch("/{channel_name}/config", status_code=200)
async def update_channel_config(
    channel_name: str,
    config: dict[str, object],
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Update channel configuration (permission control, session settings, etc.)."""
    from app.database.models import UserConfig

    row = (
        await db.execute(
            select(UserConfig).where(
                UserConfig.config_key == "channels",
            )
        )
    ).scalar_one_or_none()

    if row and isinstance(row.config_value, dict):
        channels_config = dict(row.config_value)
    else:
        channels_config = {}

    if "channels" not in channels_config:
        channels_config["channels"] = {}

    channels_config["channels"][channel_name] = config

    version = f"{int(asyncio.get_running_loop().time() * 1000)}_0"

    if row:
        row.config_value = channels_config
        row.version = version
        row.last_device_id = "web"
    else:
        row = UserConfig(
            id=nanoid(size=16),
            config_key="channels",
            config_value=channels_config,
            version=version,
            last_device_id="web",
            is_encrypted=False,
        )
        db.add(row)

    await db.commit()

    return {"status": "updated", "message": "Channel configuration updated"}
