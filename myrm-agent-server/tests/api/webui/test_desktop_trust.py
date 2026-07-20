"""Tests for GET/DELETE /webui/desktop/trust/apps."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(webui=True)


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.mark.asyncio
async def test_list_trusted_apps_empty(client: httpx.AsyncClient, tmp_path: Path) -> None:
    with patch("app.platform_utils.workspace_root.get_workspace_root", return_value=str(tmp_path)):
        response = await client.get("/webui/desktop/trust/apps")
    assert response.status_code == 200
    assert response.json()["apps"] == []


@pytest.mark.asyncio
async def test_list_and_revoke_trusted_apps(client: httpx.AsyncClient, tmp_path: Path) -> None:
    approval_dir = tmp_path / ".agent" / "desktop_control"
    approval_dir.mkdir(parents=True)
    (approval_dir / "approved_apps.json").write_text(
        json.dumps(
            {
                "apps": {
                    "safari": {
                        "scope": "always",
                        "display_name": "Safari",
                        "app_id": "",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with patch("app.platform_utils.workspace_root.get_workspace_root", return_value=str(tmp_path)):
        list_response = await client.get("/webui/desktop/trust/apps")
        assert list_response.status_code == 200
        apps = list_response.json()["apps"]
        assert len(apps) == 1
        assert apps[0]["trust_key"] == "safari"

        revoke_response = await client.request(
            "DELETE",
            "/webui/desktop/trust/apps",
            json={"trust_key": "safari"},
        )
        assert revoke_response.status_code == 200

        empty_response = await client.get("/webui/desktop/trust/apps")
        assert empty_response.json()["apps"] == []


@pytest.mark.asyncio
async def test_revoke_missing_returns_404(client: httpx.AsyncClient, tmp_path: Path) -> None:
    with patch("app.platform_utils.workspace_root.get_workspace_root", return_value=str(tmp_path)):
        response = await client.request(
            "DELETE",
            "/webui/desktop/trust/apps",
            json={"trust_key": "missing"},
        )
    assert response.status_code == 404
