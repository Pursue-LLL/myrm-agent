"""Tests for channel inbound profile resolution."""

from app.channels.inbound_profile import resolve_channel_ingress_mode


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
