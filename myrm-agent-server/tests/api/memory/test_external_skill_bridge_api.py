# [POS] tests/api/memory/test_external_skill_bridge_api.py
# [INPUT] FastAPI, httpx.AsyncClient, tmp_path, app.api.memory.external_bridge
# [OUTPUT] TestExternalSkillBridgeAPISuite

"""Integration tests for external agent skill bridge and memory gateway API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.external_bridge import router as external_bridge_router
from app.services.memory.skill_bridge import get_external_skill_bridge_service


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting external bridge router."""
    api_app = FastAPI()
    api_app.include_router(external_bridge_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset service in-memory collections before each test."""
    service = get_external_skill_bridge_service()
    service._contributed_facts.clear()
    service._seed_default_facts()


@pytest.mark.asyncio
async def test_list_targets_api(test_app: FastAPI, tmp_path: Path) -> None:
    """Verify endpoint lists all supported external agent targets."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/memory/external/targets",
            params={"workspace_root": str(tmp_path)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_supported"] >= 5
        agent_types = [t["agent_type"] for t in data["targets"]]
        assert "cursor" in agent_types
        assert "claude_code" in agent_types
        assert "codex" in agent_types
        assert "hermes" in agent_types
        assert "openclaw" in agent_types


@pytest.mark.asyncio
async def test_install_and_idempotent_bridge_api(test_app: FastAPI, tmp_path: Path) -> None:
    """Verify installing bridge into target file and idempotency on repeat call."""
    target_file = tmp_path / ".cursorrules"
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First install
        install_payload = {
            "agent_type": "cursor",
            "custom_target_path": str(target_file),
            "api_base_url": "http://127.0.0.1:8000",
            "read_only": False,
            "max_recalled_facts": 5,
        }
        res1 = await client.post("/api/memory/external/install", json=install_payload)
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["success"] is True
        assert d1["action"] == "created"
        assert target_file.exists()

        content = target_file.read_text(encoding="utf-8")
        assert "<!-- MYRM_MEMORY_BRIDGE_START -->" in content
        assert "<!-- MYRM_MEMORY_BRIDGE_END -->" in content

        # Repeated install -> unchanged
        res2 = await client.post("/api/memory/external/install", json=install_payload)
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["success"] is True
        assert d2["action"] == "unchanged"


@pytest.mark.asyncio
async def test_uninstall_bridge_api(test_app: FastAPI, tmp_path: Path) -> None:
    """Verify safe uninstallation of bridge delimiter block."""
    target_file = tmp_path / "CLAUDE.md"
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Install first
        await client.post(
            "/api/memory/external/install",
            json={
                "agent_type": "claude_code",
                "custom_target_path": str(target_file),
            },
        )
        assert target_file.exists()

        # Uninstall
        unres = await client.post(
            "/api/memory/external/uninstall",
            json={
                "agent_type": "claude_code",
                "custom_target_path": str(target_file),
            },
        )
        assert unres.status_code == 200
        data = unres.json()
        assert data["success"] is True
        assert data["removed"] is True
        assert data["file_deleted"] is True
        assert not target_file.exists()


@pytest.mark.asyncio
async def test_query_external_memory_api(test_app: FastAPI) -> None:
    """Verify fast sub-20ms memory recall endpoint."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/memory/external/query",
            json={"query": "typing", "limit": 4},
        )
        assert res.status_code == 200
        data = res.json()
        assert "hits" in data
        assert "took_ms" in data
        assert data["took_ms"] < 200.0
        assert data["total_hits"] >= 1
        assert any("typing" in hit["text"].lower() for hit in data["hits"])


@pytest.mark.asyncio
async def test_contribute_external_memory_api_redaction_and_blocking(test_app: FastAPI) -> None:
    """Verify credential scrubbing on contribution and rejection of high-entropy raw secrets."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Case 1: Text with recognizable API key pattern gets safely redacted
        safe_req = {
            "text": "User wants to connect to db with key ghp_1234567890abcdef1234567890abcdef123456",
            "category": "preference",
            "confidence": 0.95,
        }
        res1 = await client.post("/api/memory/external/contribute", json=safe_req)
        assert res1.status_code == 200
        d1 = res1.json()
        assert d1["accepted"] is True
        assert d1["fact_id"] is not None
        assert "ghp_" not in d1["redacted_text"]

        # Case 2: Unstructured high-entropy token gets blocked
        unsafe_req = {
            "text": "Secret raw token is 7xK9pQ2mW8vL5nB3jH1tG4dF6sA0zC9e",
            "category": "credential",
            "confidence": 1.0,
        }
        res2 = await client.post("/api/memory/external/contribute", json=unsafe_req)
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["accepted"] is False
        assert "Security violation" in (d2["reason"] or "")
