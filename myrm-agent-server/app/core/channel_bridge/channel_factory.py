"""Channel factory — instance creation with DB-backed credentials.

Delegates to the framework's ``create_channels`` for bulk instantiation
and provides ``create_channel_instance`` for multi-account support.

[INPUT]
- app.channels.core::create_channels, resolve_credentials
- app.core.channel_bridge.credential_spec::load_from_db, is_channel_enabled

[OUTPUT]
- create_all_channels() -> AsyncGenerator[BaseChannel]
- create_channel_instance() -> BaseChannel (for multi-instance)

[POS]
Business-layer assembly. Bridges framework channel factory with
application-specific DB credential source and lifecycle management.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncGenerator

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import resolve_credentials
from app.channels.core.factory import create_channels
from app.channels.providers.registry import (
    get_channel_class_safe,
    registered_names,
)
from app.channels.types import ChannelStatus
from app.core.channel_bridge.credential_spec import is_channel_enabled, load_from_db

logger = logging.getLogger(__name__)


async def create_all_channels() -> AsyncGenerator[BaseChannel, None]:
    """Instantiate all channels, resolving credentials from DB/env.

    Yields ``BaseChannel`` instances ready for Gateway registration.
    Disabled channels are yielded with ``ChannelStatus.DISABLED`` pre-set
    so that Gateway registers them (for status visibility) without starting.
    ON_DEMAND channels (e.g. WhatsApp) are yielded normally; Gateway respects
    their start_mode and only starts them when should_auto_start() is True.
    """
    from app.core.channel_bridge.providers.chat import ChatChannel

    yield ChatChannel()

    from app.channels.providers.webhook import WebhookChannel

    yield WebhookChannel()

    # Temporarily disabled for E2E testing - WhatsApp bridge causes startup hang
    # from app.channels.providers.whatsapp import WhatsAppChannel
    # yield WhatsAppChannel()

    from app.channels.providers.wechat.ilink_channel import WeChatILinkChannel

    yield WeChatILinkChannel()

    channels = await create_channels(source=load_from_db, skip_empty=False)

    for _name, channel in channels.items():
        spec = channel.credential_spec
        if spec is not None:
            enabled = await is_channel_enabled(spec.config_key)
            if not enabled:
                channel._status = ChannelStatus.DISABLED

        yield channel


def generate_instance_id() -> str:
    """Generate a short, stable instance ID (6 hex chars)."""
    return secrets.token_hex(3)


_SESSION_BOUND_KEYS: dict[str, set[str]] = {
    "wechat": {"bot_token", "ilink_bot_id", "ilink_user_id"},
}


def _strip_login_credentials_for_new_instance(
    channel_type: str,
    kwargs: dict[str, object],
) -> None:
    """Clear session-bound credentials so a new instance starts unauthenticated.

    Shared configuration (e.g. base_url, api_url) is preserved.
    """
    keys_to_clear = _SESSION_BOUND_KEYS.get(channel_type)
    if not keys_to_clear:
        return
    for key in keys_to_clear:
        if key in kwargs:
            kwargs[key] = ""


async def create_channel_instance(
    channel_type: str,
    instance_id: str,
    credentials: dict[str, str] | None = None,
) -> BaseChannel:
    """Create a new channel instance with a unique name for multi-instance support.

    The instance's ``name`` attribute is set to ``{channel_type}_{instance_id}``
    so it can be registered alongside the default instance in the Gateway.

    Args:
        channel_type: Base channel type (e.g., "wechat", "telegram")
        instance_id: Unique instance identifier (e.g., from generate_instance_id())
        credentials: Optional credential overrides; if None, resolves from DB/env

    Returns:
        A BaseChannel instance with a unique name, ready for Gateway.add_channel()

    Raises:
        ValueError: If the channel type is not found in registry
    """
    if channel_type not in registered_names():
        raise ValueError(f"Unknown channel type: {channel_type}")

    cls = get_channel_class_safe(channel_type)
    if cls is None:
        raise ValueError(f"Channel type '{channel_type}' unavailable (missing SDK?)")

    spec = cls.credential_spec
    if credentials is not None:
        creds = credentials
    elif spec is not None:
        creds = await resolve_credentials(spec, load_from_db)
        kwargs_dict = dict(creds)
        _strip_login_credentials_for_new_instance(channel_type, kwargs_dict)
        creds = {k: str(v) for k, v in kwargs_dict.items()}
    else:
        creds = {}

    channel = cls.from_credentials(creds) if creds else cls()
    channel.channel_type = channel_type
    channel.name = f"{channel_type}_{instance_id}"
    return channel


# ── Instance persistence (UserConfig-backed) ──────────────────────

_INSTANCES_CONFIG_ID = "channel-instances"
_INSTANCES_CONFIG_KEY = "channelInstances"


async def load_persisted_instances() -> list[dict[str, str]]:
    """Load the persisted channel instances list from UserConfig."""
    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import UserConfig

    async with get_session() as session:
        row = (await session.execute(select(UserConfig).where(UserConfig.id == _INSTANCES_CONFIG_ID))).scalar_one_or_none()
        if row and isinstance(row.config_value, dict):
            raw = row.config_value.get("instances", [])
            if isinstance(raw, list):
                out: list[dict[str, str]] = []
                for it in raw:
                    if isinstance(it, dict):
                        out.append({str(k): str(v) for k, v in it.items()})
                return out
    return []


async def save_persisted_instances(instances: list[dict[str, str]]) -> None:
    """Save the channel instances list to UserConfig."""
    import asyncio

    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import UserConfig

    version = f"{int(asyncio.get_running_loop().time() * 1000)}_0"
    async with get_session() as session:
        row = (await session.execute(select(UserConfig).where(UserConfig.id == _INSTANCES_CONFIG_ID))).scalar_one_or_none()
        if row:
            row.config_value = {"instances": instances}
            row.version = version
        else:
            session.add(
                UserConfig(
                    id=_INSTANCES_CONFIG_ID,
                    config_key=_INSTANCES_CONFIG_KEY,
                    config_value={"instances": instances},
                    version=version,
                    last_device_id="channel-instance-mgr",
                    is_encrypted=False,
                )
            )
        await session.commit()
