"""Cloudflare Pages poll_status integration tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.hosting.providers.cloudflare_pages import CloudflarePagesProvider
from app.services.hosting.types import HostingTarget


@pytest.mark.asyncio
async def test_cloudflare_poll_status_maps_success_to_ready() -> None:
    provider = CloudflarePagesProvider()
    target = HostingTarget(
        id="cf-1",
        name="CF Pages",
        provider_type="cloudflare_pages",
        config={"account_id": "acc_123", "project_name": "demo"},
        is_default=False,
    )
    request = httpx.Request(
        "GET",
        "https://api.cloudflare.com/client/v4/accounts/acc_123/pages/projects/demo/deployments/dep_cf",
    )
    response = httpx.Response(
        200,
        json={"result": {"latest_stage": {"status": "success"}, "url": "demo.pages.dev"}},
        request=request,
    )

    async def handler(req: httpx.Request) -> httpx.Response:
        return response

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.hosting.providers.cloudflare_pages.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        result = await provider.poll_status(
            target=target,
            credentials={"api_token": "cf_token"},
            publication_id="dep_cf",
            project_ref="demo",
        )

    assert result["status"] == "READY"
    assert result["url"] == "https://demo.pages.dev"
