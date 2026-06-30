"""Vercel hosting provider tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.hosting.packager import PublishFile
from app.services.hosting.providers.vercel import VercelHostingProvider, sanitize_vercel_project_name
from app.services.hosting.types import HostingTarget


def test_sanitize_vercel_project_name_fallback() -> None:
    assert sanitize_vercel_project_name("", "abcdef12-3456") == "myrm-artifact-abcdef12"


@pytest.mark.asyncio
async def test_vercel_test_connection_requires_token() -> None:
    provider = VercelHostingProvider()
    target = HostingTarget(id="v1", name="V", provider_type="vercel", config={}, is_default=False)
    ok, message = await provider.test_connection(target, {})
    assert ok is False


@pytest.mark.asyncio
async def test_vercel_publish_success() -> None:
    provider = VercelHostingProvider()
    target = HostingTarget(id="v1", name="V", provider_type="vercel", config={}, is_default=False)
    mock_client = AsyncMock()
    mock_client.deploy = AsyncMock(
        return_value={"url": "https://demo.vercel.app", "deployment_id": "dep_v1", "project_id": "prj_v1", "status": "READY"}
    )

    with patch("app.services.hosting.providers.vercel.VercelClient", return_value=mock_client):
        result = await provider.publish(
            target=target,
            credentials={"token": "vercel_tok"},
            artifact_id="art-1",
            artifact_name="My Demo",
            files={"index.html": PublishFile(path="index.html", content="<html/>")},
            existing_project_ref=None,
        )

    assert result.success is True
    assert result.url == "https://demo.vercel.app"


@pytest.mark.asyncio
async def test_vercel_publish_handles_deploy_exception() -> None:
    provider = VercelHostingProvider()
    target = HostingTarget(id="v1", name="V", provider_type="vercel", config={}, is_default=False)
    mock_client = AsyncMock()
    mock_client.deploy = AsyncMock(side_effect=RuntimeError("deploy boom"))

    with patch("app.services.hosting.providers.vercel.VercelClient", return_value=mock_client):
        result = await provider.publish(
            target=target,
            credentials={"token": "vercel_tok"},
            artifact_id="art-1",
            artifact_name="Demo",
            files={"index.html": PublishFile(path="index.html", content="<html/>")},
            existing_project_ref="prj_old",
        )

    assert result.success is False
    assert "deploy boom" in result.error


@pytest.mark.asyncio
async def test_vercel_poll_status() -> None:
    provider = VercelHostingProvider()
    target = HostingTarget(id="v1", name="V", provider_type="vercel", config={}, is_default=False)
    mock_client = AsyncMock()
    mock_client.get_deployment_status = AsyncMock(return_value={"id": "dep_1", "url": "https://x.vercel.app", "status": "READY"})

    with patch("app.services.hosting.providers.vercel.VercelClient", return_value=mock_client):
        status = await provider.poll_status(
            target=target,
            credentials={"token": "vercel_tok"},
            publication_id="dep_1",
        )

    assert status["status"] == "READY"
    assert status["url"] == "https://x.vercel.app"
