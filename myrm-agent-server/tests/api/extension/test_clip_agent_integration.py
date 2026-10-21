"""Integration tests for /extension/clip-agent — real ConfigService, no router mocks."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.database.connection import get_session
from app.database.models import ConfigAuditLog, UserConfig
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="extension")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with patch(
        "app.core.security.auth.identity.is_loopback_ip",
        return_value=True,
    ):
        yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
async def cleanup_extension_clip_config() -> Iterator[None]:
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    yield
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


@pytest.mark.integration
def test_clip_agent_get_put_roundtrip_persists_config(client: TestClient) -> None:
    """GET/PUT must survive ConfigRecord validation (ConfigKey SSOT)."""
    empty = client.get("/api/v1/extension/clip-agent")
    assert empty.status_code == 200, empty.text
    assert empty.json() == {"agent_id": None, "web_ui_origin": None}

    updated = client.put(
        "/api/v1/extension/clip-agent",
        json={
            "agent_id": "agent-wiki-writer",
            "web_ui_origin": "http://127.0.0.1:3000",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["agent_id"] == "agent-wiki-writer"
    assert body["web_ui_origin"] == "http://127.0.0.1:3000"

    reread = client.get("/api/v1/extension/clip-agent")
    assert reread.status_code == 200, reread.text
    assert reread.json() == body
