# [POS]: tests/api/memory/test_failure_search_api.py
# [INPUT]: app.api.memory.failure_search_router, FastAPI app
# [OUTPUT]: Integration API tests for FailureTriggeredHistoricalSessionRetrievalSuite (Item 109)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import FailureOutcomeType, HistoricalResolutionEntry

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


def _index(
    service: FailureSearchService,
    *,
    entry_id: str,
    session_id: str,
    error_signature: str,
    outcome_type: FailureOutcomeType,
    solution_snippet: str,
    explanation: str,
    turn_index: int = 1,
    confidence: float = 0.9,
) -> None:
    """Seed one historical resolution straight into the service's search engine."""
    service._search_engine.index_resolution(
        HistoricalResolutionEntry(
            entry_id=entry_id,
            session_id=session_id,
            turn_index=turn_index,
            error_signature=error_signature,
            outcome_type=outcome_type,
            solution_snippet=solution_snippet,
            explanation=explanation,
            confidence=confidence,
        )
    )


@pytest.fixture
def test_app(isolated_service: FailureSearchService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(failure_search_router, prefix="/api/memory")
    app.dependency_overrides[get_failure_search_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_list_resolutions_api(test_app: FastAPI, isolated_service: FailureSearchService) -> None:
    """Validate listing indexed resolution entries via REST API."""
    _index(
        isolated_service,
        entry_id="res-fix-001",
        session_id="sess-hist-999",
        turn_index=4,
        error_signature="ConnectionRefusedError: dial tcp 127.0.0.1:5432 connect: connection refused",
        outcome_type=FailureOutcomeType.SUCCESSFUL_RESOLUTION,
        solution_snippet="docker-compose up -d postgres && wait-for-it 5432",
        explanation="PostgreSQL daemon was not started before database migration command",
        confidence=0.95,
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        list_res = await client.get("/api/memory/failure-search/resolutions")
        assert list_res.status_code == 200
        by_id = {item["entry_id"]: item for item in list_res.json()}
        assert by_id["res-fix-001"]["session_id"] == "sess-hist-999"
        assert by_id["res-fix-001"]["outcome_type"] == "successful_resolution"


@pytest.mark.asyncio
async def test_dual_track_failure_query_api(test_app: FastAPI, isolated_service: FailureSearchService) -> None:
    """Validate dual-track similarity query returning both successful and cautionary entries."""
    _index(
        isolated_service,
        entry_id="res-fix-003",
        session_id="sess-prev-101",
        turn_index=5,
        error_signature="git lock index.lock FileExistsError unable to create index.lock",
        outcome_type=FailureOutcomeType.SUCCESSFUL_RESOLUTION,
        solution_snippet="rm -f .git/index.lock",
        explanation="Stale lock file from crashed git process",
    )
    _index(
        isolated_service,
        entry_id="res-caut-001",
        session_id="sess-prev-102",
        turn_index=3,
        error_signature="git lock index.lock FileExistsError unable to create index.lock",
        outcome_type=FailureOutcomeType.CAUTIONARY_FAILURE,
        solution_snippet="git checkout -f main",
        explanation="Disastrous attempt: discarded uncommitted modifications without removing the lock",
        confidence=0.85,
    )
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Query using raw error trace
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
