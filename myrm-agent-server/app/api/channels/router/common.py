"""[OUTPUT]
- router / logger / channel config helpers

[POS]
Shared primitives of the channel management router.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.channels.schemas import (
    ChannelIssueResponse,
)
from app.channels.types import ChannelIssue

_CHANNEL_CONFIG_KEYS: dict[str, str] = {
    "feishu": "feishuCredentials",
    "dingtalk": "dingtalkCredentials",
    "slack": "slackCredentials",
    "qq": "qqCredentials",
    "discord": "discordCredentials",
    "wecom": "wecomCredentials",
    "wecom_aibot": "wecomAibotCredentials",
    "teams": "teamsCredentials",
    "matrix": "matrixCredentials",
    "telegram": "telegramCredentials",
    "googlechat": "googlechatCredentials",
    "wechat": "wechatCredentials",
    "wechat_official": "wechatOfficialCredentials",
    "whatsapp": "whatsappCredentials",
    "voice": "voiceCredentials",
    "signal": "signalCredentials",
    "line": "lineCredentials",
    "imessage": "imessageCredentials",
    "irc": "ircCredentials",
    "zalo": "zaloCredentials",
    "email": "emailCredentials",
    "mattermost": "mattermostCredentials",
    "onebot": "onebotCredentials",
    "sms": "smsCredentials",
}


router = APIRouter()
logger = logging.getLogger(__name__)


def _channel_config_key(channel_name: str) -> str | None:
    """Map a channel name to its credential config_key in UserConfig."""
    return _CHANNEL_CONFIG_KEYS.get(channel_name)


def _issues_to_response(issues: list[ChannelIssue]) -> list[ChannelIssueResponse]:
    return [
        ChannelIssueResponse(
            kind=i.kind,
            severity=i.severity,
            message=i.message,
            fix=i.fix,
        )
        for i in issues
    ]


def _merged_issues_for_channel(
    channel_name: str,
    *,
    probe_map: dict[str, list[ChannelIssue]] | None = None,
) -> list[ChannelIssue]:
    from app.channels.providers.registry import probe_sdk_channel_issues
    from app.core.channel_bridge import channel_gateway
    from app.services.channels.sdk_registration import merge_channel_issues

    bus_issues = channel_gateway.collect_all_issues().get(channel_name, [])
    resolved_probe = probe_map if probe_map is not None else probe_sdk_channel_issues()
    probe_issues = resolved_probe.get(channel_name, [])
    return merge_channel_issues(bus_issues, probe_issues)


def channel_credentials_key(channel_name: str) -> str:
    """Resolve the UserConfig config_key for a channel or instance credentials.

    Default channels use the registered mapping (e.g. ``wechatCredentials``);
    instance channels (``{type}_{instance_id}``) fall back to
    ``{channel_name}Credentials``.
    """
    from app.channels.core.credentials import channel_credentials_config_key

    return channel_credentials_config_key(channel_name, _CHANNEL_CONFIG_KEYS)
