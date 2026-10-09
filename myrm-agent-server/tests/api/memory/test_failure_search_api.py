# [POS]: tests/api/memory/test_failure_search_api.py
# [INPUT]: app.api.memory.failure_search_router, FastAPI app
# [OUTPUT]: Integration API tests for FailureTriggeredHistoricalSessionRetrievalSuite (Item 109)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.failure_search_router import (
    router as failure_search_router,
)
from app.services.memory.failure_search_service import (
    FailureSearchService,
    get_failure_search_service,
)


@pytest.fixture
def isolated_service() -> FailureSearchService:
    """Provides an isolated in-memory FailureSearchService instance."""
    return FailureSearchService()


@pytest.fixture
def test_app(isolated_service: FailureSearchService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(failure_search_router, prefix="/api/memory")
    app.dependency_overrides[get_failure_search_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_index_and_list_resolutions_api(test_app: FastAPI) -> None:
    """Validate indexing resolution entries and retrieving the list via REST API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Index a successful resolution
        create_res = await client.post(
            "/api/memory/failure-search/resolutions",
            json={
                "entry_id": "res-fix-001",
                "session_id": "sess-hist-999",
                "turn_index": 4,
                "error_signature": "ConnectionRefusedError: dial tcp 127.0.0.1:5432 connect: connection refused",
                "outcome_type": "successful_resolution",
                "solution_snippet": "docker-compose up -d postgres && wait-for-it 5432",
                "explanation": "PostgreSQL daemon was not started before database migration command",
                "confidence": 0.95,
            },
        )
        assert create_res.status_code == 201
        data = create_res.json()
        assert data["entry_id"] == "res-fix-001"
        assert data["session_id"] == "sess-hist-999"
        assert data["outcome_type"] == "successful_resolution"

        # 2. List entries
        list_res = await client.get("/api/memory/failure-search/resolutions")
        assert list_res.status_code == 200
        items = list_res.json()
        assert len(items) >= 1
        assert any(item["entry_id"] == "res-fix-001" for item in items)


@pytest.mark.asyncio
async def test_direct_session_resolution_read_api(test_app: FastAPI) -> None:
    """Validate directly reading resolution snippet from session without guessing."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Prepopulate entry
        await client.post(
            "/api/memory/failure-search/resolutions",
            json={
                "entry_id": "res-fix-002",
                "session_id": "session-target-777",
                "turn_index": 2,
                "error_signature": "ModuleNotFoundError: No module named 'pydantic_settings'",
                "outcome_type": "successful_resolution",
                "solution_snippet": "poetry add pydantic-settings",
                "explanation": "Pydantic V2 moved BaseSettings to pydantic-settings package",
                "confidence": 1.0,
            },
        )

        # Direct read existing session
        res = await client.get("/api/memory/failure-search/resolutions/session-target-777")
        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == "session-target-777"
        assert "pydantic-settings" in data["solution_snippet"]

        # Read non-existing session returns 404
        not_found_res = await client.get("/api/memory/failure-search/resolutions/session-nonexistent-000")
        assert not_found_res.status_code == 404


@pytest.mark.asyncio
async def test_dual_track_failure_query_api(test_app: FastAPI) -> None:
    """Validate dual-track similarity query returning both successful and cautionary entries."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Index a successful solution
        await client.post(
            "/api/memory/failure-search/resolutions",
            json={
                "entry_id": "res-fix-003",
                "session_id": "sess-prev-101",
                "turn_index": 5,
                "error_signature": "git lock index.lock FileExistsError unable to create index.lock",
                "outcome_type": "successful_resolution",
                "solution_snippet": "rm -f .git/index.lock",
                "explanation": "Stale lock file from crashed git process",
                "confidence": 0.9,
            },
        )

        # 2. Index a cautionary failure
        await client.post(
            "/api/memory/failure-search/resolutions",
            json={
                "entry_id": "res-caut-001",
                "session_id": "sess-prev-102",
                "turn_index": 3,
                "error_signature": "git lock index.lock FileExistsError unable to create index.lock",
                "outcome_type": "cautionary_failure",
                "solution_snippet": "git checkout -f main",
                "explanation": "Disastrous attempt: discarded uncommitted modifications without removing the lock",
                "confidence": 0.85,
            },
        )

        # 3. Query using raw error trace
        query_res = await client.post(
            "/api/memory/failure-search/query",
            json={
                "error_message": "fatal: Unable to create '.git/index.lock': File exists.",
                "tool_name": "bash",
                "exit_code": 128,
                "top_n": 3,
                "include_cautionary": True,
            },
        )
        assert query_res.status_code == 200
        body = query_res.json()
        assert body["total_matched"] >= 1
        assert len(body["successful_resolutions"]) >= 1
        assert "rm -f .git/index.lock" in body["successful_resolutions"][0]["solution_snippet"]
        assert len(body["cautionary_failures"]) >= 1
        assert "git checkout -f main" in body["cautionary_failures"][0]["solution_snippet"]
        assert "曾成功解决同类错误" in body["suggested_action"]


@pytest.mark.asyncio
async def test_failure_interceptor_and_prompt_injection_api(test_app: FastAPI) -> None:
    """Validate intercepting tool failure and producing formatted prompt injection block."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Prepopulate historical solution
        await client.post(
            "/api/memory/failure-search/resolutions",
            json={
                "entry_id": "res-fix-004",
                "session_id": "sess-inter-55",
                "turn_index": 1,
                "error_signature": "PermissionDeniedError chmod +x script.sh EACCES",
                "outcome_type": "successful_resolution",
                "solution_snippet": "chmod +x run.sh && ./run.sh",
                "explanation": "Script executable bit was missing",
                "confidence": 1.0,
            },
        )

        # 1. Intercept matching error
        intercept_res = await client.post(
            "/api/memory/failure-search/intercept",
            json={
                "tool_name": "bash",
                "error_content": "bash: ./run.sh: Permission denied (errno 13 EACCES)",
                "exit_code": 126,
            },
        )
        assert intercept_res.status_code == 200
        data = intercept_res.json()
        assert data["should_inject"] is True
        assert "FAILURE SELF-HEALING ADVICE" in data["injected_prompt_block"]
        assert "chmod +x run.sh" in data["injected_prompt_block"]

        # 2. Intercept unmatched error
        unmatched_res = await client.post(
            "/api/memory/failure-search/intercept",
            json={
                "tool_name": "unknown_tool",
                "error_content": "ArbitraryUnseenCustomException: totally unindexed error occurred",
                "exit_code": 1,
            },
        )
        assert unmatched_res.status_code == 200
        unmatched_data = unmatched_res.json()
        assert unmatched_data["should_inject"] is False
        assert unmatched_data["injected_prompt_block"] == ""


@pytest.mark.asyncio
async def test_config_get_and_update_api(test_app: FastAPI) -> None:
    """Validate retrieving and mutating failure search configuration."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get active config
        get_res = await client.get("/api/memory/failure-search/config")
        assert get_res.status_code == 200
        cfg = get_res.json()
        assert cfg["enabled"] is True

        # Update config
        put_res = await client.put(
            "/api/memory/failure-search/config",
            json={
                "enabled": False,
                "auto_trigger_on_error": False,
                "max_matches": 5,
                "min_similarity_threshold": 0.25,
                "include_cautionary_failures": False,
            },
        )
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["enabled"] is False
        assert updated["auto_trigger_on_error"] is False
        assert updated["max_matches"] == 5
        assert updated["min_similarity_threshold"] == 0.25
        assert updated["include_cautionary_failures"] is False
