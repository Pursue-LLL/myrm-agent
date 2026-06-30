"""SSRF guard tests for webhook publication egress."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.hosting.ssrf_guard import SSRFValidationError, validate_webhook_url


def test_validate_webhook_url_blocks_localhost() -> None:
    with pytest.raises(SSRFValidationError):
        validate_webhook_url("https://127.0.0.1/hook")


def test_validate_webhook_url_blocks_private_ip_resolution() -> None:
    with patch("app.services.hosting.ssrf_guard.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("10.0.0.1", 0))]):
        with pytest.raises(SSRFValidationError):
            validate_webhook_url("https://internal.example/hook")


@pytest.mark.asyncio
async def test_webhook_client_does_not_follow_redirect_to_private_ip() -> None:
    from app.services.hosting.providers.http_webhook import HttpWebhookProvider
    from app.services.hosting.packager import PublishFile
    from app.services.hosting.types import HostingTarget

    provider = HttpWebhookProvider()
    target = HostingTarget(
        id="wh-1",
        name="Webhook",
        provider_type="http_webhook",
        config={"webhook_url": "https://safe.example/hook"},
        is_default=False,
    )
    files = {"index.html": PublishFile(path="index.html", content="<html/>")}

    request = httpx.Request("POST", "https://safe.example/hook")
    response = httpx.Response(302, headers={"location": "http://127.0.0.1/evil"}, request=request)

    async def handler(request: httpx.Request) -> httpx.Response:
        return response

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.providers.http_webhook.validate_webhook_url", return_value="https://safe.example/hook"):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            result = await provider.publish(
                target=target,
                credentials={},
                artifact_id="art-1",
                artifact_name="demo",
                files=files,
                existing_project_ref=None,
            )

    assert result.success is False
    assert result.status == "ERROR"
