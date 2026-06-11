"""Channel inbound transport profiles for Ingress requirement resolution.

[INPUT]
- app.channels.providers.registry::CHANNEL_META (POS: Central registry for all channel providers)

[OUTPUT]
- InboundMode: outbound | inbound | conditional classification
- CHANNEL_INBOUND_SPECS: per-channel config key + configured field
- resolve_channel_ingress_mode: map stored credentials to outbound/inbound

[POS]
Single source of truth for which channels need public Ingress when configured.
Consumed by app.core.infra.ingress_requirement and channel status issue supplements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

IngressTransport = Literal["outbound", "inbound"]


class InboundMode(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    CONDITIONAL = "conditional"


@dataclass(frozen=True, slots=True)
class ChannelInboundSpec:
    mode: InboundMode
    config_key: str | None = None
    configured_field: str | None = None


CHANNEL_INBOUND_SPECS: dict[str, ChannelInboundSpec] = {
    "telegram": ChannelInboundSpec(InboundMode.CONDITIONAL, "telegramCredentials", "botToken"),
    "feishu": ChannelInboundSpec(InboundMode.CONDITIONAL, "feishuCredentials", "appId"),
    "slack": ChannelInboundSpec(InboundMode.CONDITIONAL, "slackCredentials", "botToken"),
    "discord": ChannelInboundSpec(InboundMode.CONDITIONAL, "discordCredentials", "botToken"),
    "dingtalk": ChannelInboundSpec(InboundMode.OUTBOUND, "dingtalkCredentials", "clientId"),
    "wecom_aibot": ChannelInboundSpec(InboundMode.OUTBOUND, "wecomAibotCredentials", "botId"),
    "whatsapp": ChannelInboundSpec(InboundMode.OUTBOUND, None, None),
    "wechat": ChannelInboundSpec(InboundMode.OUTBOUND, "wechatCredentials", "botId"),
    "imessage": ChannelInboundSpec(InboundMode.OUTBOUND, "imessageCredentials", "apiUrl"),
    "line": ChannelInboundSpec(InboundMode.INBOUND, "lineCredentials", "channelAccessToken"),
    "sms": ChannelInboundSpec(InboundMode.INBOUND, "smsCredentials", "accountSid"),
    "wecom": ChannelInboundSpec(InboundMode.INBOUND, "wecomCredentials", "corpId"),
    "teams": ChannelInboundSpec(InboundMode.INBOUND, "teamsCredentials", "appId"),
    "googlechat": ChannelInboundSpec(InboundMode.INBOUND, "googlechatCredentials", "serviceAccountJson"),
    "matrix": ChannelInboundSpec(InboundMode.INBOUND, "matrixCredentials", "homeserver"),
    "mattermost": ChannelInboundSpec(InboundMode.INBOUND, "mattermostCredentials", "serverUrl"),
    "email": ChannelInboundSpec(InboundMode.INBOUND, "emailCredentials", "imapHost"),
    "signal": ChannelInboundSpec(InboundMode.INBOUND, "signalCredentials", "phoneNumber"),
    "irc": ChannelInboundSpec(InboundMode.INBOUND, "ircCredentials", "server"),
    "zalo": ChannelInboundSpec(InboundMode.INBOUND, "zaloCredentials", "oaId"),
    "qq": ChannelInboundSpec(InboundMode.INBOUND, "qqCredentials", "appId"),
    "onebot": ChannelInboundSpec(InboundMode.INBOUND, "onebotCredentials", "host"),
    "voice": ChannelInboundSpec(InboundMode.INBOUND, "twilioCredentials", "accountSid"),
    "github": ChannelInboundSpec(InboundMode.INBOUND, "githubCredentials", "webhookSecret"),
}


def _field_value(creds: dict[str, object], field: str) -> str:
    raw = creds.get(field)
    if raw is None:
        snake = "".join(f"_{c.lower()}" if c.isupper() else c for c in field).lstrip("_")
        raw = creds.get(snake)
    if raw is None:
        return ""
    return str(raw).strip()


def is_channel_configured(creds: dict[str, object] | None, field: str | None) -> bool:
    if not creds or not field:
        return False
    return bool(_field_value(creds, field))


def resolve_channel_ingress_mode(channel: str, creds: dict[str, object] | None) -> IngressTransport | None:
    """Return outbound/inbound for a configured channel, or None if not configured."""
    spec = CHANNEL_INBOUND_SPECS.get(channel)
    if spec is None:
        return None
    if spec.config_key and not is_channel_configured(creds, spec.configured_field):
        return None

    if spec.mode == InboundMode.OUTBOUND:
        return "outbound"
    if spec.mode == InboundMode.INBOUND:
        return "inbound"

    if not creds:
        return "outbound"

    if channel == "feishu":
        transport = _field_value(creds, "transport") or "websocket"
        return "inbound" if transport == "webhook" else "outbound"
    if channel == "telegram":
        webhook = _field_value(creds, "webhookUrl") or _field_value(creds, "webhook_url")
        return "inbound" if webhook else "outbound"
    if channel == "slack":
        app_token = _field_value(creds, "appToken") or _field_value(creds, "app_token")
        return "outbound" if app_token else "inbound"
    if channel == "discord":
        enable_gateway = creds.get("enableGateway", creds.get("enable_gateway", True))
        return "outbound" if bool(enable_gateway) else "inbound"

    return "outbound"
