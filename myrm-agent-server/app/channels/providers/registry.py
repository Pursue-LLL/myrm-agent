"""Channel provider registry — lazy-loading, thread-safe, zero overhead for unused channels.

Only ``import``s a channel module when that channel is first requested.
Channels that are never configured consume zero memory.

Supports both built-in channels and custom channel registration via
``register_custom_channel()`` for user-defined providers.

Usage:
    from app.channels.providers.registry import (
        get_channel_class,
        load_enabled_channels,
        register_custom_channel,
        CHANNEL_META,
    )

    cls = get_channel_class("discord")            # lazy import + cache
    channels = load_enabled_channels(config)       # bulk load enabled ones

    # Register a custom channel without modifying framework code
    register_custom_channel("my_channel", ChannelSpec(
        module="my_package.channels.my_channel",
        class_name="MyChannel",
        display_name="My Channel",
    ))

[INPUT]
(no external dependencies)

[OUTPUT]
- ChannelSpec: Import path + class name for a channel provider
- get_channel_class / get_channel_class_safe: Lazy-load channel class by name
- get_channel_spec / channel_install_command: Spec lookup and GUI install hints
- probe_sdk_channel_issues: DEPENDENCY diagnostics when optional SDK import fails
- load_enabled_channels: Bulk load enabled channels from config
- register_custom_channel: Register a user-defined channel provider
- CHANNEL_META: Read-only snapshot of all registered channel specs

[POS]
Central registry for all channel providers. Built-in channels use relative
imports within the providers package; custom channels use absolute module paths.
"""

from __future__ import annotations

import importlib
import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.channels.core.base import BaseChannel

logger = logging.getLogger(__name__)

_CHANNEL_INSTALL_HINTS: dict[str, str] = {
    "matrix": "uv sync --extra matrix",
    "discord": "uv sync --extra channels-sdk",
    "feishu": "uv sync --extra channels-sdk",
}

# Built-in channels with harness lazy-install mapping (see dependency_install.py).
_LAZY_SDK_CHANNEL_NAMES: frozenset[str] = frozenset({"matrix", "discord", "feishu"})


def get_channel_spec(name: str) -> ChannelSpec | None:
    """Return the registry spec for *name*, or ``None`` if unknown."""
    return _all_specs().get(name)


def channel_install_command(channel_name: str) -> str:
    """Return the ``uv sync`` hint for optional SDK channels."""
    spec = get_channel_spec(channel_name)
    if spec is None or not spec.sdk_package:
        return ""
    return _CHANNEL_INSTALL_HINTS.get(channel_name, "uv sync")


def _channel_install_hint(channel_name: str, spec: ChannelSpec | None) -> str:
    """Human-readable install hint when a channel module fails to import."""
    if spec is None or not spec.sdk_package:
        return ""
    command = channel_install_command(channel_name)
    return f" (run: {command})"


def probe_sdk_channel_issues() -> dict[str, list[ChannelIssue]]:
    """Detect missing optional SDK imports for lazy-install channel types."""
    from app.channels.types import ChannelIssue, IssueKind, IssueSeverity

    issues_map: dict[str, list[ChannelIssue]] = {}
    for name in sorted(_LAZY_SDK_CHANNEL_NAMES):
        spec = _BUILTIN_SPECS.get(name)
        if spec is None or not spec.sdk_package:
            continue
        if get_channel_class_safe(name) is not None:
            continue
        command = channel_install_command(name)
        issues_map[name] = [
            ChannelIssue(
                kind=IssueKind.DEPENDENCY,
                severity=IssueSeverity.ERROR,
                message=f"{spec.sdk_package} not installed. Run: {command}",
                fix=command,
            )
        ]
    return issues_map


@dataclass(frozen=True, slots=True)
class ChannelSpec:
    """Import path + class name for a single channel provider.

    For built-in channels, ``module`` is a relative path within the providers package.
    For custom channels, ``module`` must be an absolute dotted module path
    (e.g. ``"my_package.channels.custom"``).
    """

    module: str
    class_name: str
    display_name: str
    sdk_package: str | None = None


_BUILTIN_SPECS: dict[str, ChannelSpec] = {
    # Core / built-in
    "telegram": ChannelSpec(".telegram", "TelegramChannel", "Telegram"),
    "webhook": ChannelSpec(".webhook", "WebhookChannel", "Webhook"),
    "whatsapp": ChannelSpec(".whatsapp", "WhatsAppChannel", "WhatsApp"),
    # IM platforms (high-frequency)
    "discord": ChannelSpec(".discord", "DiscordChannel", "Discord", "discord.py"),
    "feishu": ChannelSpec(".feishu", "FeishuChannel", "飞书/Feishu", "lark-oapi"),
    "slack": ChannelSpec(".slack", "SlackChannel", "Slack"),
    "dingtalk": ChannelSpec(".dingtalk", "DingTalkChannel", "钉钉/DingTalk"),
    "qq": ChannelSpec(".qq", "QQChannel", "QQ"),
    "onebot": ChannelSpec(".onebot", "OneBotChannel", "QQ (OneBot/NapCat)"),
    # Enterprise / protocol
    "wecom": ChannelSpec(".wecom.channel", "WeComChannel", "企业微信-自建应用/WeCom App"),
    "wecom_aibot": ChannelSpec(".wecom.aibot_channel", "WeComAiBotChannel", "企业微信-AI Bot/WeCom AI Bot"),
    "wechat": ChannelSpec(".wechat.ilink_channel", "WeChatILinkChannel", "微信/WeChat"),
    "wechat_official": ChannelSpec(".wechat.official_channel", "WeChatOfficialChannel", "微信Official Account/WeChat Official"),
    "teams": ChannelSpec(".msteams.channel", "MSTeamsChannel", "MSTeams"),
    "googlechat": ChannelSpec(".googlechat.channel", "GoogleChatChannel", "Google Chat"),
    "matrix": ChannelSpec(".matrix", "MatrixChannel", "Matrix", "mautrix"),
    "email": ChannelSpec(".email", "EmailChannel", "Email"),
    # Supplementary
    "signal": ChannelSpec(".signal", "SignalChannel", "Signal"),
    "imessage": ChannelSpec(".imessage", "IMessageChannel", "iMessage"),
    "line": ChannelSpec(".line", "LINEChannel", "LINE"),
    "irc": ChannelSpec(".irc", "IRCChannel", "IRC"),
    "mattermost": ChannelSpec(".mattermost", "MattermostChannel", "Mattermost"),
    "zalo": ChannelSpec(".zalo", "ZaloChannel", "Zalo"),
    "voice": ChannelSpec(".voice_channel", "VoiceCallChannel", "Voice/Twilio"),
    "sms": ChannelSpec(".sms", "SMSChannel", "SMS/Twilio"),
}

_custom_specs: dict[str, ChannelSpec] = {}
_custom_lock = threading.Lock()

_cache: dict[str, type[BaseChannel]] = {}
_cache_lock = threading.Lock()


def _all_specs() -> dict[str, ChannelSpec]:
    """Merged view of built-in + custom specs (custom overrides built-in)."""
    with _custom_lock:
        if not _custom_specs:
            return _BUILTIN_SPECS
        return {**_BUILTIN_SPECS, **_custom_specs}


CHANNEL_META: dict[str, ChannelSpec] = dict(_BUILTIN_SPECS)


def register_custom_channel(name: str, spec: ChannelSpec) -> None:
    """Register a custom channel provider.

    Custom channels use absolute module paths (not relative to providers package).
    If *name* collides with a built-in, the custom spec takes precedence.

    Example::

        register_custom_channel("my_sms", ChannelSpec(
            module="my_app.channels.sms",
            class_name="SMSChannel",
            display_name="SMS",
        ))
    """
    with _custom_lock:
        if name in _custom_specs:
            logger.warning("Custom channel '%s' already registered, replacing", name)
        _custom_specs[name] = spec

    with _cache_lock:
        _cache.pop(name, None)

    CHANNEL_META[name] = spec
    logger.info("Custom channel registered: %s (%s)", name, spec.display_name)


def get_channel_class(name: str) -> type[BaseChannel]:
    """Lazy-load and cache a channel class by registry name.

    Raises ``KeyError`` if *name* is not in the registry.
    Raises ``ImportError`` / ``AttributeError`` if the provider module
    or class cannot be imported (e.g. missing SDK dependency).
    """
    with _cache_lock:
        if name in _cache:
            return _cache[name]

    specs = _all_specs()
    spec = specs[name]

    is_relative = spec.module.startswith(".")
    mod = importlib.import_module(spec.module, package=__package__ if is_relative else None)
    cls = getattr(mod, spec.class_name)

    with _cache_lock:
        _cache[name] = cls
    return cls


def get_channel_class_safe(name: str) -> type[BaseChannel] | None:
    """Same as ``get_channel_class`` but returns ``None`` on import failure."""
    try:
        return get_channel_class(name)
    except (KeyError, ImportError, AttributeError) as exc:
        logger.debug("Channel '%s' unavailable: %s", name, exc)
        return None


def load_enabled_channels(
    channel_configs: dict[str, dict[str, object]],
) -> dict[str, type[BaseChannel]]:
    """Load channel classes for all entries in *channel_configs* whose
    ``enabled`` key is truthy.  Channels with missing SDKs are skipped
    with a warning.

    Returns: ``{channel_name: channel_class}``
    """
    specs = _all_specs()
    result: dict[str, type[BaseChannel]] = {}
    for name, cfg in channel_configs.items():
        if not cfg.get("enabled", False):
            continue
        cls = get_channel_class_safe(name)
        if cls is None:
            spec = specs.get(name)
            install_hint = _channel_install_hint(name, spec)
            logger.warning("Channel '%s' enabled but import failed%s", name, install_hint)
            continue
        result[name] = cls
    return result


def registered_names() -> frozenset[str]:
    """All channel names known to the registry (regardless of availability)."""
    return frozenset(_all_specs())


def clear_cache() -> None:
    """Reset the import cache. Primarily for tests."""
    with _cache_lock:
        _cache.clear()


def clear_custom_channels() -> None:
    """Remove all custom channel registrations and restore CHANNEL_META to built-in only.

    Primarily for tests.
    """
    with _custom_lock:
        names = list(_custom_specs.keys())
        _custom_specs.clear()
    with _cache_lock:
        for name in names:
            _cache.pop(name, None)
    CHANNEL_META.clear()
    CHANNEL_META.update(_BUILTIN_SPECS)
