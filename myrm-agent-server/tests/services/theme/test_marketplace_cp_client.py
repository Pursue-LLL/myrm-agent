"""Tests for server-side CP marketplace client helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.theme.package.marketplace_cp_client import verify_marketplace_entitlement


@pytest.mark.asyncio
async def test_verify_entitlement_skips_when_cp_not_configured_local() -> None:
    with (
        patch("app.services.theme.package.marketplace_cp_client._cp_base_url", return_value=""),
        patch(
            "app.services.theme.package.marketplace_cp_client.get_deployment_capabilities",
        ) as mock_caps,
    ):
        mock_caps.return_value.is_sandbox_instance = False
        assert await verify_marketplace_entitlement(listing_id="listing-1") is True


@pytest.mark.asyncio
async def test_verify_entitlement_fail_closed_in_sandbox_without_cp() -> None:
    with (
        patch("app.services.theme.package.marketplace_cp_client._cp_base_url", return_value=""),
        patch(
            "app.services.theme.package.marketplace_cp_client.get_deployment_capabilities",
        ) as mock_caps,
    ):
        mock_caps.return_value.is_sandbox_instance = True
        assert await verify_marketplace_entitlement(listing_id="listing-1") is False


@pytest.mark.asyncio
async def test_verify_entitlement_returns_api_result() -> None:
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: {"entitled": False}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with (
        patch("app.services.theme.package.marketplace_cp_client._cp_base_url", return_value="http://cp"),
        patch(
            "app.services.theme.package.marketplace_cp_client._internal_headers",
            return_value={"X-Telemetry-Token": "t"},
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        assert await verify_marketplace_entitlement(listing_id="listing-1") is False
