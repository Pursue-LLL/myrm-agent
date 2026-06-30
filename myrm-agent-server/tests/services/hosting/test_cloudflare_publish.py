"""Cloudflare Pages publish and connection tests."""

from __future__ import annotations

import base64
from unittest.mock import patch

import httpx
import pytest

from app.services.hosting.packager import PublishFile
from app.services.hosting.providers.cloudflare_pages import CloudflarePagesProvider
from app.services.hosting.types import HostingTarget


@pytest.mark.asyncio
async def test_cloudflare_test_connection_success() -> None:
    provider = CloudflarePagesProvider()
    target = HostingTarget(
        id="cf-1",
        name="CF",
        provider_type="cloudflare_pages",
        config={"account_id": "acc_1"},
        is_default=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": True}, request=request)

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.hosting.providers.cloudflare_pages.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        ok, message = await provider.test_connection(target, {"api_token": "tok"})
    assert ok is True
    assert "valid" in message.lower()


@pytest.mark.asyncio
async def test_cloudflare_test_connection_missing_token() -> None:
    provider = CloudflarePagesProvider()
    target = HostingTarget(id="cf", name="CF", provider_type="cloudflare_pages", config={"account_id": "a"}, is_default=False)
    ok, message = await provider.test_connection(target, {})
    assert ok is False
    assert "token" in message.lower()


@pytest.mark.asyncio
async def test_cloudflare_publish_creates_project_and_deploys() -> None:
    provider = CloudflarePagesProvider()
    target = HostingTarget(
        id="cf-1",
        name="CF",
        provider_type="cloudflare_pages",
        config={"account_id": "acc_1", "project_name": "demo-site"},
        is_default=False,
    )
    files = {
        "index.html": PublishFile(path="index.html", content="<html/>"),
        "logo.png": PublishFile(path="logo.png", content=base64.b64encode(b"\x89PNG").decode(), encoding="base64"),
    }
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method + " " + request.url.path)
        if request.method == "POST" and request.url.path.endswith("/pages/projects"):
            return httpx.Response(200, json={"result": {"name": "demo-site"}}, request=request)
        if request.method == "POST" and "/deployments" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "result": {
                        "id": "dep_cf",
                        "aliases": ["demo.pages.dev"],
                        "latest_stage": {"status": "success"},
                    }
                },
                request=request,
            )
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.hosting.providers.cloudflare_pages.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        result = await provider.publish(
            target=target,
            credentials={"api_token": "cf_tok"},
            artifact_id="art-1",
            artifact_name="Demo",
            files=files,
            existing_project_ref=None,
        )

    assert result.success is True
    assert result.publication_id == "dep_cf"
    assert result.url == "https://demo.pages.dev"
    assert any("POST" in c for c in calls)


@pytest.mark.asyncio
async def test_cloudflare_publish_reuses_existing_project() -> None:
    provider = CloudflarePagesProvider()
    target = HostingTarget(
        id="cf-1",
        name="CF",
        provider_type="cloudflare_pages",
        config={"account_id": "acc_1"},
        is_default=False,
    )
    files = {"index.html": PublishFile(path="index.html", content="<html/>")}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/deployments" in request.url.path:
            return httpx.Response(
                200,
                json={"result": {"id": "dep_2", "aliases": ["existing.pages.dev"], "latest_stage": {"status": "success"}}},
                request=request,
            )
        return httpx.Response(404, request=request)

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.hosting.providers.cloudflare_pages.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        result = await provider.publish(
            target=target,
            credentials={"api_token": "cf_tok"},
            artifact_id="art-1",
            artifact_name="Demo",
            files=files,
            existing_project_ref="existing",
        )

    assert result.success is True
    assert result.project_ref == "existing"


@pytest.mark.asyncio
async def test_cloudflare_poll_status_failure_stage() -> None:
    provider = CloudflarePagesProvider()
    target = HostingTarget(
        id="cf-1",
        name="CF",
        provider_type="cloudflare_pages",
        config={"account_id": "acc_1", "project_name": "demo"},
        is_default=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"result": {"latest_stage": {"status": "failure"}, "url": "fail.pages.dev"}},
            request=request,
        )

    transport = httpx.MockTransport(handler)
    with patch(
        "app.services.hosting.providers.cloudflare_pages.httpx.AsyncClient",
        return_value=httpx.AsyncClient(transport=transport, follow_redirects=False),
    ):
        result = await provider.poll_status(
            target=target,
            credentials={"api_token": "cf_tok"},
            publication_id="dep_fail",
            project_ref="demo",
        )

    assert result["status"] == "ERROR"
