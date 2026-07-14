"""Tests for DB-backed channel enablement."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel_bridge.credential_spec import is_channel_enabled


@pytest.mark.asyncio
async def test_channel_without_credentials_is_disabled() -> None:
    with patch(
        "app.core.channel_bridge.credential_spec.load_from_db",
        new=AsyncMock(return_value=None),
    ):
        enabled = await is_channel_enabled("onebotCredentials")

    assert enabled is False


@pytest.mark.asyncio
async def test_channel_with_explicit_disabled_flag_is_disabled() -> None:
    with patch(
        "app.core.channel_bridge.credential_spec.load_from_db",
        new=AsyncMock(return_value={"enabled": False}),
    ):
        enabled = await is_channel_enabled("onebotCredentials")

    assert enabled is False


@pytest.mark.asyncio
async def test_configured_channel_without_enabled_flag_is_enabled() -> None:
    with patch(
        "app.core.channel_bridge.credential_spec.load_from_db",
        new=AsyncMock(return_value={"port": "3001"}),
    ):
        enabled = await is_channel_enabled("onebotCredentials")

    assert enabled is True
