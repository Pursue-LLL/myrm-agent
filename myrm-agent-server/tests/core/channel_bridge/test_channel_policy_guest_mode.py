"""Tests for SqlChannelPolicyProvider guest mode credential reads."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel_bridge.channel_policy import SqlChannelPolicyProvider


@pytest.mark.asyncio
async def test_get_guest_mode_false_for_non_telegram() -> None:
    provider = SqlChannelPolicyProvider()
    assert await provider.get_guest_mode("slack") is False


@pytest.mark.asyncio
async def test_get_guest_mode_reads_bool_from_credentials() -> None:
    provider = SqlChannelPolicyProvider()
    with patch.object(
        provider,
        "_load_credential_config",
        AsyncMock(return_value={"guestMode": True}),
    ):
        assert await provider.get_guest_mode("telegram") is True


@pytest.mark.asyncio
async def test_get_guest_mode_parses_string_truthy_values() -> None:
    provider = SqlChannelPolicyProvider()
    with patch.object(
        provider,
        "_load_credential_config",
        AsyncMock(return_value={"guestMode": "yes"}),
    ):
        assert await provider.get_guest_mode("telegram") is True


@pytest.mark.asyncio
async def test_get_guest_mode_false_when_credentials_missing() -> None:
    provider = SqlChannelPolicyProvider()
    with patch.object(provider, "_load_credential_config", AsyncMock(return_value=None)):
        assert await provider.get_guest_mode("telegram") is False
