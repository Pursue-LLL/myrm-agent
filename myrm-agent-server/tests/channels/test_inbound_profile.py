"""Tests for channel inbound profile resolution."""

import pytest

from app.channels.protocols.inbound_profile import resolve_channel_ingress_mode


@pytest.mark.parametrize(
    ("channel", "creds"),
    [
        ("email", {"imapHost": "imap.example.com"}),
        ("irc", {"server": "irc.example.com"}),
        ("mattermost", {"serverUrl": "https://mm.example.com"}),
        ("signal", {"phoneNumber": "+15551234567"}),
        ("qq", {"appId": "102000000"}),
        ("matrix", {"homeserverUrl": "https://matrix.example.com"}),
    ],
)
def test_active_outbound_channels_do_not_require_ingress(channel: str, creds: dict[str, object]) -> None:
    # These channels receive via outbound connections (IMAP poll / TCP / WS /
    # local CLI) and must never be flagged as needing public Ingress.
    assert resolve_channel_ingress_mode(channel, creds) == "outbound"


def test_feishu_websocket_is_outbound() -> None:
    mode = resolve_channel_ingress_mode(
        "feishu",
        {"appId": "id", "transport": "websocket"},
    )
    assert mode == "outbound"


def test_feishu_webhook_is_inbound() -> None:
    mode = resolve_channel_ingress_mode(
        "feishu",
        {"appId": "id", "transport": "webhook"},
    )
    assert mode == "inbound"


def test_teams_configured_is_inbound() -> None:
    mode = resolve_channel_ingress_mode(
        "teams",
        {"appId": "id", "appPassword": "pw"},
    )
    assert mode == "inbound"


def test_dingtalk_is_outbound_when_configured() -> None:
    mode = resolve_channel_ingress_mode(
        "dingtalk",
        {"clientId": "id"},
    )
    assert mode == "outbound"


def test_unconfigured_returns_none() -> None:
    assert resolve_channel_ingress_mode("line", {"channelAccessToken": ""}) is None


def test_wechat_official_configured_is_inbound() -> None:
    mode = resolve_channel_ingress_mode("wechat_official", {"appId": "wx123"})
    assert mode == "inbound"


def test_wechat_official_unconfigured_returns_none() -> None:
    assert resolve_channel_ingress_mode("wechat_official", None) is None


def test_webhook_is_outbound_when_enabled() -> None:
    assert resolve_channel_ingress_mode("webhook", None) == "outbound"


def test_zalo_configured_is_inbound() -> None:
    # Zalo receives via webhook callback (zalo.py:3) and its credential is accessToken.
    assert resolve_channel_ingress_mode("zalo", {"accessToken": "za-123"}) == "inbound"


def test_wechat_configured_is_outbound() -> None:
    # WeChat (ilink) connects outbound via bot token; configured via botToken.
    assert resolve_channel_ingress_mode("wechat", {"botToken": "bt"}) == "outbound"


def test_matrix_configured_is_outbound() -> None:
    # Matrix (mautrix client) connects to homeserver; configured via homeserverUrl.
    assert resolve_channel_ingress_mode("matrix", {"homeserverUrl": "https://m.example.com"}) == "outbound"


@pytest.mark.parametrize(
    ("channel", "configured_field"),
    [
        ("telegram", "botToken"),
        ("feishu", "appId"),
        ("slack", "botToken"),
        ("discord", "botToken"),
        ("dingtalk", "clientId"),
        ("wecom_aibot", "botId"),
        ("wechat", "botToken"),
        ("wechat_official", "appId"),
        ("imessage", "apiUrl"),
        ("line", "channelAccessToken"),
        ("sms", "accountSid"),
        ("wecom", "corpId"),
        ("teams", "appId"),
        ("googlechat", "serviceAccountJson"),
        ("matrix", "homeserverUrl"),
        ("mattermost", "serverUrl"),
        ("email", "imapHost"),
        ("signal", "phoneNumber"),
        ("irc", "server"),
        ("zalo", "accessToken"),
        ("qq", "appId"),
        ("onebot", "host"),
        ("voice", "accountSid"),
        ("github", "webhookSecret"),
    ],
)
def test_configured_field_is_recognized(channel: str, configured_field: str) -> None:
    # Any channel whose configured_field is present must resolve to a mode (not None),
    # so an active channel is never silently skipped during Ingress assessment.
    assert resolve_channel_ingress_mode(channel, {configured_field: "x"}) is not None


def test_inbound_specs_cover_all_registry_channels() -> None:
    from app.channels.protocols.inbound_profile import CHANNEL_INBOUND_SPECS
    from app.channels.providers.registry import _BUILTIN_SPECS

    # Guard against drift: every built-in channel must declare an Ingress profile.
    # Compare against the built-in snapshot (not CHANNEL_META, which grows with
    # runtime-registered custom channels and would cause false positives).
    assert set(CHANNEL_INBOUND_SPECS) == set(_BUILTIN_SPECS)
