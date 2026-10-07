# [POS] tests/api/memory/test_world_model_api.py
# [INPUT] FastAPI, httpx.AsyncClient, tmp_path, app.api.memory.world_model
# [OUTPUT] TestWorldModelAPISuite

"""Integration tests for L3 World Model macro memory query and environment sync API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.world_model import router as world_model_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting world-model router."""
    api_app = FastAPI()
    api_app.include_router(world_model_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_query_empty_world_model(test_app: FastAPI) -> None:
    """Verify querying an unconfigured project returns clean default baseline."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/world-model/query",
            json={"project_id": "fresh_test_project"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "fresh_test_project"
        assert data["version"] == 1
        assert data["has_active_constraints"] is False
        assert "[NO_MACRO_CONSTRAINTS_DEFINED]" in data["rendered_markdown"]
        assert "<!-- L3_WORLD_MODEL_BEGIN -->" in data["rendered_markdown"]
        assert "<!-- L3_WORLD_MODEL_END -->" in data["rendered_markdown"]


@pytest.mark.asyncio
async def test_update_macro_dimensions_and_fetch_fields(test_app: FastAPI) -> None:
    """Verify updating individual dimensions directly updates entity state."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Update general rules
        resp1 = await client.post(
            "/api/memory/world-model/update",
            json={
                "project_id": "proj_demo",
                "field_name": "general_rules_and_safety_constraints",
                "content": "Constraint: Absolute zero Any types across codebase.",
                "source_ref": "governance_spec",
            },
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["version"] == 2
        assert data1["field_name"] == "general_rules_and_safety_constraints"

        # Update architecture contract
        resp2 = await client.post(
            "/api/memory/world-model/update",
            json={
                "project_id": "proj_demo",
                "field_name": "project_contract",
                "content": "Contract: Server imports only exported Harness facade.",
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["version"] == 3

        # Fetch fields
        resp3 = await client.get(
            "/api/memory/world-model/fields",
            params={"project_id": "proj_demo"},
        )
        assert resp3.status_code == 200
        fields = resp3.json()
        assert "zero Any" in fields["general_rules"]
        assert "Harness facade" in fields["project_contract"]


@pytest.mark.asyncio
async def test_sync_workspace_environment(test_app: FastAPI, tmp_path: Path) -> None:
    """Verify workspace probing extracts runtimes and syncs into world model."""
    # Setup mock workspace files
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo-app"\nrequires-python = ">=3.13"\ndependencies = ["fastapi", "pydantic"]\n',
        encoding="utf-8",
    )
    pkg_json = tmp_path / "package.json"
    pkg_json.write_text(
        '{"name": "demo-web", "dependencies": {"react": "^19.0.0", "vite": "^6.0.0"}}\n',
        encoding="utf-8",
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/world-model/sync",
            json={"project_id": "synced_proj", "workspace_root": str(tmp_path)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["project_id"] == "synced_proj"
        assert len(data["detected_runtimes"]) == 2
        runtime_names = [r["name"] for r in data["detected_runtimes"]]
        assert "Python" in runtime_names
        assert "Node.js" in runtime_names
        assert "pyproject.toml" in data["config_markers"]
        assert "package.json" in data["config_markers"]


@pytest.mark.asyncio
async def test_query_with_workspace_auto_sync(test_app: FastAPI, tmp_path: Path) -> None:
    """Verify /query endpoint automatically probes and injects workspace profile when provided."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "auto-sync-app"\nrequires-python = ">=3.13"\ndependencies = ["uvicorn"]\n',
        encoding="utf-8",
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/world-model/query",
            json={"project_id": "auto_proj", "workspace_root": str(tmp_path)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_active_constraints"] is True
        assert "Python" in data["rendered_markdown"]
        assert "auto-sync-app" in data["rendered_markdown"]
        assert "<!-- L3_WORLD_MODEL_BEGIN -->" in data["rendered_markdown"]
