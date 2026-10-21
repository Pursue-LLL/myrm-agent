"""Unit tests for Subagent Bounded Structured Failure Facts & Safe Diagnostic Protocol API endpoints.

[INPUT]
- app.api.agents.failure_facts_router.router
- app.services.agent.failure_facts_service.FailureFactsService

[OUTPUT]
- Pytest test cases verifying error diagnosis, credential scrubbing, standard header generation, history query, and session cleanup.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_failure_facts_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.failure_facts_router import (
    get_failure_facts_service,
)
from app.api.agents.failure_facts_router import (
    router as failure_facts_router,
)
from app.services.agent.failure_facts_service import FailureFactsService


@pytest.fixture
def mock_failure_service() -> FailureFactsService:
    return FailureFactsService()


@pytest.fixture
def failure_client(
    mock_failure_service: FailureFactsService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(failure_facts_router)
    app.dependency_overrides[get_failure_facts_service] = lambda: mock_failure_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_diagnose_failure_api(failure_client: TestClient) -> None:
    chat_id = "chat_test_facts_01"
    payload = {
        "product": "claude-code-worker",
        "stage": "turn",
        "raw_message": (
            "Execution aborted with Bearer super-secret-token. "
            "Secret configured: api_key='sk-ant-0123456789abcdef'. "
            "Stack traceback at /Users/developer/projects/subagent/runner.py line 42."
        ),
        "http_status": 400,
        "category": "contextWindowExceeded",
        "metadata": {
            "sandbox_path": "/Users/developer/sandboxes/session_101",
        },
    }

    resp = failure_client.post(f"/chats/{chat_id}/subagents/diagnose-failure", json=payload)
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["product"] == "claude-code-worker"
    assert data["stage"] == "turn"
    assert data["category"] == "contextWindowExceeded"
    assert data["remediation"] == "compact_and_resume"
    assert data["safe_diagnostic_header"] == (
        "Product subagent failure (product: claude-code-worker; "
        "stage: turn; category: contextWindowExceeded; HTTP status: 400; "
        "exit code: none; signal: none)"
    )

    # Privacy scrubbing assertions
    assert "super-secret-token" not in data["sanitized_message"]
    assert "Bearer [REDACTED_TOKEN]" in data["sanitized_message"]
    assert "sk-ant-0123456789abcdef" not in data["sanitized_message"]
    assert "[PATH_REDACTED]/runner.py" in data["sanitized_message"]
    assert "/Users/developer" not in data["sanitized_message"]
    assert "[PATH_REDACTED]/session_101" in data["metadata"]["sandbox_path"]


def test_failure_facts_history_and_cleanup_api(failure_client: TestClient) -> None:
    chat_id = "chat_test_facts_02"

    # 1. Record failure 1 (Rate limit)
    failure_client.post(
        f"/chats/{chat_id}/subagents/diagnose-failure",
        json={
            "product": "worker_ratelimit",
            "stage": "query-start",
            "raw_message": "Upstream OpenAI API rate limit exceeded (429)",
            "http_status": 429,
        },
    )

    # 2. Record failure 2 (Timeout)
    failure_client.post(
        f"/chats/{chat_id}/subagents/diagnose-failure",
        json={
            "product": "worker_timeout",
            "stage": "process",
            "raw_message": "Socket connection timed out after 30000ms",
            "http_status": 504,
        },
    )

    # 3. Query history
    resp_hist = failure_client.get(f"/chats/{chat_id}/subagents/failure-facts")
    assert resp_hist.status_code == 200
    hist_data = resp_hist.json()["data"]
    assert hist_data["total_count"] == 2
    assert len(hist_data["facts"]) == 2
    assert hist_data["facts"][0]["category"] == "rateLimited"
    assert hist_data["facts"][1]["category"] == "networkTimeout"

    # 4. Cleanup
    resp_del = failure_client.delete(f"/chats/{chat_id}/subagents/failure-facts")
    assert resp_del.status_code == 200
    assert resp_del.json()["data"]["cleaned"] is True

    # 5. Query after cleanup
    resp_empty = failure_client.get(f"/chats/{chat_id}/subagents/failure-facts")
    assert resp_empty.json()["data"]["total_count"] == 0
    assert len(resp_empty.json()["data"]["facts"]) == 0
