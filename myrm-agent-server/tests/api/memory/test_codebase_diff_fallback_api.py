"""Integration and unit tests for codebase diff fallback API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.codebase_diff_router import router as codebase_diff_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create lightweight test FastAPI application hosting the codebase diff router."""
    api_app = FastAPI()
    api_app.include_router(codebase_diff_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_codebase_diff_health(test_app: FastAPI) -> None:
    """Test health check liveness probe endpoint."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/memory/codebase-diff/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "codebase_diff"


@pytest.mark.asyncio
async def test_codebase_diff_parse_numstat(test_app: FastAPI) -> None:
    """Test parsing raw git numstat lines into structured entries."""
    numstat_raw = (
        "30\t10\tsrc/core/engine.py\n"
        "-\t-\tassets/icon.png\n"
        "15\t5\tsrc/old.py => src/new.py\n"
        "200\t50\tpnpm-lock.yaml\n"
    )
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/codebase-diff/parse-numstat",
            json={"numstat_content": numstat_raw},
        )
        assert response.status_code == 200
        body = response.json()
        entries = body["entries"]
        assert len(entries) == 4

        # Verify core code
        e0 = entries[0]
        assert e0["path"] == "src/core/engine.py"
        assert e0["additions"] == 30
        assert e0["deletions"] == 10
        assert e0["category"] == "core_code"

        # Verify asset binary
        e1 = entries[1]
        assert e1["path"] == "assets/icon.png"
        assert e1["category"] == "asset_binary"

        # Verify rename
        e2 = entries[2]
        assert e2["path"] == "src/new.py"
        assert e2["old_path"] == "src/old.py"
        assert e2["is_renamed"] is True

        # Verify lockfile
        e3 = entries[3]
        assert e3["path"] == "pnpm-lock.yaml"
        assert e3["category"] == "lockfile"
        assert e3["is_generated"] is True


@pytest.mark.asyncio
async def test_codebase_diff_evaluate_micro(test_app: FastAPI) -> None:
    """Test evaluating small diff resulting in Micro tier."""
    payload = {
        "files": [
            {
                "path": "src/utils.py",
                "additions": 20,
                "deletions": 5,
                "category": "core_code",
                "patch_snippet": "def add(a, b): return a + b",
            },
            {
                "path": "tests/test_utils.py",
                "additions": 15,
                "deletions": 0,
                "category": "core_code",
            },
        ],
        "commit_message": "test: add utils test",
    }
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/codebase-diff/evaluate",
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        verdict = body["verdict"]

        assert verdict["tier"] == "micro"
        assert verdict["is_truncated"] is False
        assert verdict["total_files"] == 2
        assert verdict["total_additions"] == 35
        assert verdict["total_deletions"] == 5
        assert verdict["active_files_count"] == 2
        assert "full_fidelity_ast_retained" in verdict["applied_optimizations"]
        assert "src/utils.py" in verdict["summary_text"]


@pytest.mark.asyncio
async def test_codebase_diff_evaluate_truncation_detection(test_app: FastAPI) -> None:
    """Test truncation detection when PR declared count exceeds payload files."""
    payload = {
        "files": [
            {"path": f"src/comp_{i}.py", "additions": 10, "deletions": 2}
            for i in range(5)
        ],
        "declared_total_files": 40,  # 35 files missing, API truncated
    }
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/codebase-diff/evaluate",
            json=payload,
        )
        assert response.status_code == 200
        body = response.json()
        verdict = body["verdict"]

        assert verdict["tier"] == "massive"
        assert verdict["is_truncated"] is True
        assert verdict["truncation_reason"] is not None
        assert "File list truncated" in verdict["truncation_reason"]
        assert "truncation_guard_activated" in verdict["applied_optimizations"]
