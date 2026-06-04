"""Context bundle API tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.context.router import router as context_bundle_router


@pytest.fixture
def context_app(tmp_path: Path) -> FastAPI:
    app = FastAPI()
    app.include_router(context_bundle_router, prefix="/api/v1")
    with patch.multiple(
        "app.config.settings.settings.database",
        state_dir=str(tmp_path),
        memory_base_path=str(tmp_path / "memory"),
        harness_dir=str(tmp_path / "harness"),
    ):
        yield app


@pytest.mark.asyncio
async def test_get_context_bundle_health(context_app: FastAPI, tmp_path: Path) -> None:
    transport = ASGITransport(app=context_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/context-bundle")
    assert response.status_code == 200
    payload = response.json()
    assert payload["bundle_id"] == "default"
    assert payload["schema_version"] == 1
    assert payload["memory_base_path"] == str(tmp_path / "memory")


@pytest.mark.asyncio
async def test_apply_context_bundle_migration(context_app: FastAPI, tmp_path: Path) -> None:
    transport = ASGITransport(app=context_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/context-bundle/migrate/apply")
    assert response.status_code == 200
    payload = response.json()
    assert payload["manifest_exists"] is True
    assert (tmp_path / "context_bundle_manifest.json").is_file()
