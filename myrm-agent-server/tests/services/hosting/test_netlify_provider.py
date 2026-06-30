"""Unit tests for Netlify hosting provider."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.hosting.packager import PublishFile
from app.services.hosting.providers.netlify import NetlifyHostingProvider
from app.services.hosting.types import HostingTarget


@pytest.mark.asyncio
async def test_netlify_publish_success() -> None:
    provider = NetlifyHostingProvider()
    target = HostingTarget(
        id="netlify-1",
        name="Netlify",
        provider_type="netlify",
        config={"site_id": "site_123"},
        is_default=False,
    )
    files = {"index.html": PublishFile(path="index.html", content="<html/>")}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"id": "dep_n1", "ssl_url": "https://site.netlify.app", "state": "ready"},
                request=request,
            )
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.hosting.providers.netlify.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        result = await provider.publish(
            target=target,
            credentials={"access_token": "nl_tok"},
            artifact_id="art-1",
            artifact_name="demo",
            files=files,
            existing_project_ref=None,
        )

    assert result.success is True
    assert result.url == "https://site.netlify.app"


@pytest.mark.asyncio
async def test_netlify_poll_status_ready() -> None:
    provider = NetlifyHostingProvider()
    target = HostingTarget(id="n1", name="N", provider_type="netlify", config={}, is_default=False)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"state": "ready", "ssl_url": "https://ready.netlify.app"},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.hosting.providers.netlify.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        status = await provider.poll_status(
            target=target,
            credentials={"access_token": "nl_tok"},
            publication_id="dep_n1",
        )

    assert status["status"] == "ready"
    assert status["url"] == "https://ready.netlify.app"


@pytest.mark.asyncio
async def test_netlify_test_connection_success() -> None:
    provider = NetlifyHostingProvider()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"email": "user@example.com"}, request=request)

    transport = httpx.MockTransport(handler)
    target = HostingTarget(id="n1", name="N", provider_type="netlify", config={}, is_default=False)
    with patch(
        "app.services.hosting.providers.netlify.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        ok, message = await provider.test_connection(target, {"access_token": "nl_tok"})
    assert ok is True


@pytest.mark.asyncio
async def test_netlify_publish_missing_credentials() -> None:
    provider = NetlifyHostingProvider()
    target = HostingTarget(id="n1", name="N", provider_type="netlify", config={}, is_default=False)
    result = await provider.publish(
        target=target,
        credentials={},
        artifact_id="art-1",
        artifact_name="Demo",
        files={"index.html": PublishFile(path="index.html", content="<html/>")},
        existing_project_ref=None,
    )
    assert result.success is False
