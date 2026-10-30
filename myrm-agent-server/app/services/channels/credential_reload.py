"""Apply saved channel credentials to the running gateway.

[INPUT]
- app.channels.providers.registry::get_channel_class_safe (POS: Central registry for channel providers)
- app.channels.core.credentials::resolve_credentials (POS: Framework-level credential type definitions and generic parser)
- app.core.channel_bridge.credential_spec::load_from_db, is_channel_enabled (POS: DB-backed credential loader and enabled flag)
- app.core.channel_bridge::channel_gateway (POS: Channel Gateway singleton)

[OUTPUT]
- CREDENTIAL_KEY_TO_CHANNEL: Maps the config key a credentials save arrives under to the channel it applies to
- reload_channel_credentials: Rebuild a channel from its saved credentials and swap it into the gateway

[POS]
Business-layer step that makes a credentials save take effect without a restart. Every provider that declares
credentials needs its config key in the table; ``tests/services/channels/test_credential_hot_register.py`` checks it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


CREDENTIAL_KEY_TO_CHANNEL: dict[str, str] = {
    "telegramCredentials": "telegram",
    "feishuCredentials": "feishu",
    "dingtalkCredentials": "dingtalk",
    "slackCredentials": "slack",
    "qqCredentials": "qq",
    "discordCredentials": "discord",
    "wecomCredentials": "wecom",
    "wecomAibotCredentials": "wecom_aibot",
    "teamsCredentials": "teams",
    "matrixCredentials": "matrix",
    "googlechatCredentials": "googlechat",
    "voiceCredentials": "voice",
    "signalCredentials": "signal",
    "lineCredentials": "line",
    "imessageCredentials": "imessage",
    "ircCredentials": "irc",
    "zaloCredentials": "zalo",
    "emailCredentials": "email",
    "mattermostCredentials": "mattermost",
    "wechatCredentials": "wechat",
    "wechatOfficialCredentials": "wechat_official",
    "whatsappCredentials": "whatsapp",
    "smsCredentials": "sms",
    "githubCredentials": "github",
    "onebotCredentials": "onebot",
}


async def reload_channel_credentials(config_key: str) -> None:
    """Hot-register a channel after its credentials are saved.

    If the channel is already registered in the gateway, it is atomically
    swapped via ``ChannelGateway.swap_channel`` to apply the new credentials
    (hot-reload). A failed swap restores the previous instance and re-raises
    the error so callers (e.g. the credentials endpoint) can surface it;
    non-critical lookup/parse failures are logged and swallowed.
    """
    channel_name = CREDENTIAL_KEY_TO_CHANNEL.get(config_key)
    if not channel_name:
        return

    try:
        from app.channels.core.credentials import resolve_credentials
        from app.channels.providers.registry import get_channel_class_safe
        from app.core.channel_bridge import channel_gateway
        from app.core.channel_bridge.credential_spec import (
            is_channel_enabled,
            load_from_db,
        )

        cls = get_channel_class_safe(channel_name)
        if cls is None or cls.credential_spec is None:
            return

        creds = await resolve_credentials(cls.credential_spec, load_from_db)
        if not any(creds.values()):
            return

        instance = cls.from_credentials(creds)

        enabled = await is_channel_enabled(cls.credential_spec.config_key)
        if not enabled:
            from app.channels.types import ChannelStatus

            instance._status = ChannelStatus.DISABLED
    except (ValueError, RuntimeError):
        logger.debug(
            "Hot-register channel '%s' parse failed (non-critical)",
            channel_name,
            exc_info=True,
        )
        return

    # Atomically swap the channel: resolve credentials and build the
    # replacement before touching the old instance, then keep the old
    # instance alive until the new one is successfully added. A failed swap
    # restores the previous instance and re-raises so callers (e.g. the
    # credentials endpoint) can surface the failed hot-register.
    existing = channel_gateway.bus.get_channel(channel_name)
    if existing:
        instance.display_name = existing.display_name
    await channel_gateway.swap_channel(instance, existing)
    logger.info("Channel '%s' hot-registered after credential save", channel_name)
