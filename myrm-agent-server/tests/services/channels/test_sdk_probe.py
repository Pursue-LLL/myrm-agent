"""Tests for SDK channel probe and hot-register helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.providers.registry import probe_sdk_channel_issues
from app.channels.types import IssueKind
from app.services.channels.sdk_registration import hot_register_channel, merge_channel_issues


def test_probe_sdk_channel_issues_when_import_fails() -> None:
    with patch(
        "app.channels.providers.registry.get_channel_class_safe",
        return_value=None,
    ):
        issues = probe_sdk_channel_issues()
    assert "discord" in issues
    assert issues["discord"][0].kind == IssueKind.DEPENDENCY
    assert "channels-sdk" in issues["discord"][0].fix


def test_probe_sdk_channel_issues_empty_when_import_ok() -> None:
    with patch(
        "app.channels.providers.registry.get_channel_class_safe",
        return_value=MagicMock(),
    ):
        issues = probe_sdk_channel_issues()
    assert issues == {}


def test_merge_channel_issues_dedupes() -> None:
    from app.channels.types import ChannelIssue, IssueSeverity

    a = ChannelIssue(
        kind=IssueKind.DEPENDENCY,
        severity=IssueSeverity.ERROR,
        message="m1",
        fix="uv sync --extra channels-sdk",
    )
    b = ChannelIssue(
        kind=IssueKind.DEPENDENCY,
        severity=IssueSeverity.ERROR,
        message="m2",
        fix="uv sync --extra channels-sdk",
    )
    merged = merge_channel_issues([a], [b])
    assert len(merged) == 1


@pytest.mark.asyncio
async def test_hot_register_skips_when_already_on_bus() -> None:
    mock_bus = MagicMock()
    mock_bus.get_channel.return_value = MagicMock()
    mock_gateway = MagicMock(bus=mock_bus)
    with patch("app.core.channel_bridge.channel_gateway", mock_gateway):
        ok = await hot_register_channel("discord")
    assert ok is True
    mock_bus.get_channel.assert_called_once_with("discord")


@pytest.mark.asyncio
async def test_hot_register_registers_disabled_channel() -> None:
    from app.channels.types import ChannelStatus

    mock_channel = MagicMock()
    mock_channel.name = "discord"
    mock_bus = MagicMock()
    mock_bus.get_channel.return_value = None
    mock_gateway = MagicMock(bus=mock_bus)

    with (
        patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        patch(
            "app.channels.providers.registry.get_channel_class_safe",
            return_value=MagicMock(),
        ),
        patch(
            "app.channels.core.factory.create_channels",
            new_callable=AsyncMock,
            return_value={"discord": mock_channel},
        ),
    ):
        ok = await hot_register_channel("discord")

    assert ok is True
    assert mock_channel._status == ChannelStatus.DISABLED
    mock_gateway.register.assert_called_once_with(mock_channel)
