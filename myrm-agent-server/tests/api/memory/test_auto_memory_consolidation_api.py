# [POS]: tests/api/memory/test_auto_memory_consolidation_api.py
# [INPUT]: app.api.memory.auto_memory_consolidation_router, app.services.memory.auto_memory_consolidation_service, FastAPI app
# [OUTPUT]: Integration API tests for Idle & Budget Gated Auto-Memory Consolidation Suite (Item 123)

"""Integration API tests for Idle & Budget Gated Auto-Memory Consolidation Suite (Item 123)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.auto_memory_consolidation_router import (
    router as auto_memory_consolidation_router,
)
from app.services.memory.auto_memory_consolidation_service import (
    AutoMemoryConsolidationService,
    get_auto_memory_consolidation_service,
)


@pytest.fixture
def isolated_service() -> AutoMemoryConsolidationService:
    """Provides an isolated AutoMemoryConsolidationService instance."""
    return AutoMemoryConsolidationService()


@pytest.fixture
def test_app(isolated_service: AutoMemoryConsolidationService) -> FastAPI:
    """Creates a test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(auto_memory_consolidation_router, prefix="/api/memory")
    app.dependency_overrides[get_auto_memory_consolidation_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_get_and_update_config_api(test_app: FastAPI) -> None:
    """Validate retrieving and modifying auto-consolidation threshold parameters."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get default config
        res = await client.get("/api/memory/auto-consolidation/config")
        assert res.status_code == 200
        cfg = res.json()
        assert cfg["enabled"] is True
        assert cfg["idle_timeout_seconds"] == 900.0
        assert cfg["min_turn_count"] == 3
        assert cfg["min_info_density"] == 0.35
        assert cfg["min_remaining_budget_tokens"] == 1000

        # 2. Update config
        cfg["idle_timeout_seconds"] = 300.0
        cfg["min_turn_count"] = 2
        update_res = await client.put(
            "/api/memory/auto-consolidation/config",
            json={"config": cfg},
        )
        assert update_res.status_code == 200
        updated = update_res.json()
        assert updated["idle_timeout_seconds"] == 300.0
        assert updated["min_turn_count"] == 2


@pytest.mark.asyncio
async def test_evaluate_gating_api(test_app: FastAPI) -> None:
    """Validate inspecting session admission gates."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Case A: Short trivial conversation rejected
        short_res = await client.post(
            "/api/memory/auto-consolidation/evaluate-gate",
            json={
                "session_id": "sess-eval-01",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "hi there"},
                ],
                "remaining_tokens": 10000,
                "last_active_timestamp": 0.0,
                "require_idle": False,
            },
        )
        assert short_res.status_code == 200
        short_data = short_res.json()["report"]
        assert short_data["should_consolidate"] is False
        assert short_data["turn_decision"]["passed"] is False

        # Case B: Multi-turn substantial conversation approved
        good_messages = [
            {"role": "user", "content": "Refactor database migrations to SQLite embedded engine."},
            {"role": "assistant", "content": "Created migrations with strict transaction rollback."},
            {"role": "user", "content": "Ensure zero Any types and strictly follow PEP 8 standard."},
            {"role": "assistant", "content": "Applied Pydantic V2 BaseModels with complete typing."},
            {"role": "user", "content": "We had an error with locking timeouts under concurrent tests."},
            {"role": "assistant", "content": "Resolved by enabling PRAGMA journal_mode=WAL and busy_timeout=5000."},
        ]
        ok_res = await client.post(
            "/api/memory/auto-consolidation/evaluate-gate",
            json={
                "session_id": "sess-eval-02",
                "messages": good_messages,
                "remaining_tokens": 15000,
                "last_active_timestamp": 100.0,
                "current_timestamp": 1200.0,
                "require_idle": True,
            },
        )
        assert ok_res.status_code == 200
        ok_data = ok_res.json()["report"]
        assert ok_data["should_consolidate"] is True
        assert ok_data["turn_decision"]["passed"] is True
        assert ok_data["budget_decision"]["passed"] is True
        assert ok_data["idle_state"]["is_idle_triggered"] is True


@pytest.mark.asyncio
async def test_consolidate_session_api(test_app: FastAPI) -> None:
    """Validate end-to-end session consolidation and six-dimensional artifact generation."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        messages = [
            {
                "role": "user",
                "content": "For our backend architecture, we strictly forbid backward compatibility shims.",
            },
            {
                "role": "assistant",
                "content": "Agreed. Pure refactoring principle: keep code lean, robust, and single-responsibility.",
            },
            {
                "role": "user",
                "content": "Encountered a bug where async client sessions were left unclosed causing resource leaks.",
            },
            {
                "role": "assistant",
                "content": "Fixed by wrapping AsyncClient in an async context manager block.",
            },
        ]
        tool_records = ["run_command", "replace_file_content", "run_command"]

        res = await client.post(
            "/api/memory/auto-consolidation/consolidate",
            json={
                "session_id": "sess-consolidate-03",
                "messages": messages,
                "remaining_tokens": 12000,
                "working_directory": "/Users/developer/open-perplexity",
                "tool_call_records": tool_records,
                "force_bypass_gating": True,
                "require_idle": False,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["persisted"] is True
        artifact = data["artifact"]
        assert artifact is not None
        assert artifact["session_id"] == "sess-consolidate-03"
        assert artifact["working_directory"] == "/Users/developer/open-perplexity"
        assert len(artifact["key_topics"]) >= 1
        assert len(artifact["user_preferences"]) >= 1
        assert len(artifact["failure_lessons"]) >= 1
        assert len(artifact["tool_calling_patterns"]) >= 1
        assert "Workspace: /Users/developer/open-perplexity" in artifact["summary_digest"]
