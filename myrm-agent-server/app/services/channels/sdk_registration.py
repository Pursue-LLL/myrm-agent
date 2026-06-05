"""Hot-register channel providers after lazy SDK install.

[INPUT]
- app.channels.core.factory::create_channels (POS: Framework-level channel factory)
- app.channels.providers.registry::get_channel_class_safe (POS: Central registry for channel providers)
- app.core.channel_bridge.credential_spec::load_from_db (POS: DB-backed credential loader)
- app.core.channel_bridge::channel_gateway (POS: Channel Gateway singleton)

[OUTPUT]
- hot_register_channel: Register a DISABLED channel on the gateway bus without process restart
- merge_channel_issues: Dedupe channel diagnostic issues for API responses

[POS]
Business-layer bridge between lazy dependency install and runtime channel visibility.
"""

from __future__ import annotations

import logging

from app.channels.types import ChannelIssue, ChannelStatus

logger = logging.getLogger(__name__)


def merge_channel_issues(*groups: list[ChannelIssue]) -> list[ChannelIssue]:
    """Merge issue lists, deduplicating by (kind, fix)."""
    seen: set[tuple[str, str]] = set()
    merged: list[ChannelIssue] = []
    for group in groups:
        for issue in group:
            key = (issue.kind.value, issue.fix)
            if key in seen:
                continue
            seen.add(key)
            merged.append(issue)
    return merged


async def hot_register_channel(channel_name: str) -> bool:
    """Register *channel_name* on the gateway bus if the SDK is importable.

    Creates a DISABLED instance so Settings status/toggle work without restart.
    """
    from app.channels.core.factory import create_channels
    from app.channels.providers.registry import get_channel_class_safe
    from app.core.channel_bridge import channel_gateway
    from app.core.channel_bridge.credential_spec import load_from_db

    if channel_gateway.bus.get_channel(channel_name):
        return True

    if get_channel_class_safe(channel_name) is None:
        logger.warning("Cannot hot-register channel %r: SDK still unavailable", channel_name)
        return False

    channels = await create_channels(
        source=load_from_db,
        names=frozenset({channel_name}),
        skip_empty=False,
    )
    channel = channels.get(channel_name)
    if channel is None:
        logger.warning("Cannot hot-register channel %r: factory returned no instance", channel_name)
        return False

    channel._status = ChannelStatus.DISABLED
    channel_gateway.register(channel)
    logger.info("Hot-registered channel %r (disabled, awaiting credentials)", channel_name)
    return True
