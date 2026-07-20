"""Unit tests for CP org model policy sync endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.internal.org_model_policy_sync import (
    frontend_router as org_model_policy_frontend_router,
)
from app.api.internal.org_model_policy_sync import (
    router as org_model_policy_sync_router,
)


@pytest.fixture
def policy_sync_app() -> FastAPI:
    app = FastAPI()
    app.include_router(org_model_policy_sync_router)
    app.include_router(org_model_policy_frontend_router)
    return app


@pytest.mark.asyncio
async def test_sync_stores_patterns(policy_sync_app: FastAPI) -> None:
    """POST stores patterns via ConfigService.set and returns count."""
    with patch(
        "app.api.internal.org_model_policy_sync.ConfigService",
    ) as mock_config_cls:
        mock_config = AsyncMock()
        mock_config_cls.return_value = mock_config

        with patch("app.api.internal.org_model_policy_sync.invalidate_user_configs_cache"):
            transport = ASGITransport(app=policy_sync_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/admin/org-model-policy-sync",
                    json={"allowed_patterns": ["deepseek-*", "qwen-*"]},
                )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "synced"
    assert data["pattern_count"] == 2

    saved_value = mock_config.set.await_args.kwargs["value"]
    assert saved_value["allowed_patterns"] == ["deepseek-*", "qwen-*"]
    assert mock_config.set.await_args.kwargs["device_id"] == "control_plane"


@pytest.mark.asyncio
async def test_sync_empty_patterns(policy_sync_app: FastAPI) -> None:
    """Empty pattern list clears restriction."""
    with patch(
        "app.api.internal.org_model_policy_sync.ConfigService",
    ) as mock_config_cls:
        mock_config = AsyncMock()
        mock_config_cls.return_value = mock_config

        with patch("app.api.internal.org_model_policy_sync.invalidate_user_configs_cache"):
            transport = ASGITransport(app=policy_sync_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/api/admin/org-model-policy-sync",
                    json={"allowed_patterns": []},
                )

    assert resp.status_code == 200
    assert resp.json()["pattern_count"] == 0


@pytest.mark.asyncio
async def test_get_allowed_models_no_record(policy_sync_app: FastAPI) -> None:
    """GET returns empty patterns + restricted=false when no config exists."""
    with patch(
        "app.api.internal.org_model_policy_sync.ConfigService",
    ) as mock_config_cls:
        mock_config = AsyncMock()
        mock_config.get.return_value = None
        mock_config_cls.return_value = mock_config

        transport = ASGITransport(app=policy_sync_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/org-policy/allowed-models")

    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed_patterns"] == []
    assert data["restricted"] is False


@pytest.mark.asyncio
async def test_get_allowed_models_with_patterns(policy_sync_app: FastAPI) -> None:
    """GET returns stored patterns + restricted=true."""
    mock_record = MagicMock()
    mock_record.value = {"allowed_patterns": ["gpt-4*", "claude-*"]}

    with patch(
        "app.api.internal.org_model_policy_sync.ConfigService",
    ) as mock_config_cls:
        mock_config = AsyncMock()
        mock_config.get.return_value = mock_record
        mock_config_cls.return_value = mock_config

        transport = ASGITransport(app=policy_sync_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/org-policy/allowed-models")

    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed_patterns"] == ["gpt-4*", "claude-*"]
    assert data["restricted"] is True


@pytest.mark.asyncio
async def test_sync_rejects_invalid_token(policy_sync_app: FastAPI) -> None:
    """POST with invalid CP token returns 403."""
    with patch.dict("os.environ", {"CONTROL_PLANE_TELEMETRY_TOKEN": "secret123"}):
        transport = ASGITransport(app=policy_sync_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/admin/org-model-policy-sync",
                json={"allowed_patterns": ["test-*"]},
                headers={"X-Telemetry-Token": "wrong-token"},
            )

    assert resp.status_code == 403
