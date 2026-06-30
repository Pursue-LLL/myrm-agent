"""HTTP webhook hosting provider tests."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.hosting.packager import PublishFile
from app.services.hosting.providers.http_webhook import HttpWebhookProvider
from app.services.hosting.ssrf_guard import SSRFValidationError
from app.services.hosting.types import HostingTarget


@pytest.mark.asyncio
async def test_webhook_test_connection_validates_url() -> None:
    provider = HttpWebhookProvider()
    target = HostingTarget(
        id="wh-1",
        name="Hook",
        provider_type="http_webhook",
        config={"webhook_url": "https://safe.example/hook"},
        is_default=False,
    )
    with patch("app.services.hosting.providers.http_webhook.validate_webhook_url", return_value="https://safe.example/hook"):
        ok, message = await provider.test_connection(target, {})
    assert ok is True
    assert "validated" in message.lower()


@pytest.mark.asyncio
async def test_webhook_test_connection_ssrf_rejected() -> None:
    provider = HttpWebhookProvider()
    target = HostingTarget(
        id="wh-1",
        name="Hook",
        provider_type="http_webhook",
        config={"webhook_url": "http://127.0.0.1/hook"},
        is_default=False,
    )
    ok, message = await provider.test_connection(target, {})
    assert ok is False


@pytest.mark.asyncio
async def test_webhook_publish_success() -> None:
    provider = HttpWebhookProvider()
    target = HostingTarget(
        id="wh-1",
        name="Hook",
        provider_type="http_webhook",
        config={"webhook_url": "https://safe.example/publish"},
        is_default=False,
    )
    files = {"index.html": PublishFile(path="index.html", content="<html/>")}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"url": "https://live.example.com", "publication_id": "pub_1"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.providers.http_webhook.validate_webhook_url", return_value="https://safe.example/publish"):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            result = await provider.publish(
                target=target,
                credentials={"auth_header": "X-Auth", "auth_value": "secret"},
                artifact_id="art-1",
                artifact_name="Demo",
                files=files,
                existing_project_ref=None,
            )

    assert result.success is True
    assert result.url == "https://live.example.com"


@pytest.mark.asyncio
async def test_webhook_publish_missing_url_in_response() -> None:
    provider = HttpWebhookProvider()
    target = HostingTarget(
        id="wh-1",
        name="Hook",
        provider_type="http_webhook",
        config={"webhook_url": "https://safe.example/publish"},
        is_default=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True}, request=request)

    transport = httpx.MockTransport(handler)
    with patch("app.services.hosting.providers.http_webhook.validate_webhook_url", return_value="https://safe.example/publish"):
        with patch(
            "app.services.hosting.providers.http_webhook.httpx.AsyncClient",
            return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
        ):
            result = await provider.publish(
                target=target,
                credentials={},
                artifact_id="art-1",
                artifact_name="Demo",
                files={"index.html": PublishFile(path="index.html", content="<html/>")},
                existing_project_ref=None,
            )

    assert result.success is False
    assert "url field" in result.error


@pytest.mark.asyncio
async def test_webhook_publish_missing_webhook_url() -> None:
    provider = HttpWebhookProvider()
    target = HostingTarget(id="wh", name="H", provider_type="http_webhook", config={}, is_default=False)
    result = await provider.publish(
        target=target,
        credentials={},
        artifact_id="art-1",
        artifact_name="Demo",
        files={"index.html": PublishFile(path="index.html", content="<html/>")},
        existing_project_ref=None,
    )
    assert result.success is False
    assert "webhook_url" in result.error


@pytest.mark.asyncio
async def test_webhook_poll_status_always_ready() -> None:
    provider = HttpWebhookProvider()
    target = HostingTarget(id="wh", name="H", provider_type="http_webhook", config={}, is_default=False)
    status = await provider.poll_status(target=target, credentials={}, publication_id="pub-1")
    assert status["status"] == "READY"
