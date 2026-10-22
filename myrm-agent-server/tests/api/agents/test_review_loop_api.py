"""Unit tests for Multi-Perspective Subagent Review & Bounded Review Loop API endpoints.

[INPUT]
- app.api.agents.review_loop_router.router
- app.services.agent.review_loop_service.ReviewLoopService

[OUTPUT]
- Pytest cases verifying tri-perspective review initialization,
  multi-round advance, convergence detection, max_rounds bound, and session cleanup.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_review_loop_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.review_loop_router import (
    get_review_loop_service,
)
from app.api.agents.review_loop_router import (
    router as review_loop_router,
)
from app.services.agent.review_loop_service import ReviewLoopService


@pytest.fixture
def review_service() -> ReviewLoopService:
    return ReviewLoopService()


@pytest.fixture
def review_client(
    review_service: ReviewLoopService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(review_loop_router)
    app.dependency_overrides[get_review_loop_service] = lambda: review_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_start_review_loop_clean_diff_converges(review_client: TestClient) -> None:
    chat_id = "chat_review_test_01"
    clean_diff = """
    def add(a: int, b: int) -> int:
        return a + b

    def test_add_success():
        assert add(1, 2) == 3
    """
    payload = {
        "session_id": chat_id,
        "diff_content": clean_diff,
        "context_description": "Add arithmetic addition helper",
        "max_rounds": 3,
    }

    resp = review_client.post(f"/chats/{chat_id}/review-loops/start", json=payload)
    assert resp.status_code == 200
    data = resp.json()["data"]

    assert data["session_id"] == chat_id
    assert data["status"] == "converged"
    assert data["is_clean"] is True
    assert data["current_round"] == 1
    assert data["max_rounds"] == 3
    assert len(data["rounds"]) == 1
    assert data["rounds"][0]["converged"] is True
    assert data["rounds"][0]["has_blocking_issues"] is False

    # Verify tri-perspective reports are all present
    reports = data["rounds"][0]["perspective_reports"]
    assert "correctness" in reports
    assert "test_coverage" in reports
    assert "simplicity" in reports
    assert reports["correctness"]["approved"] is True
    assert reports["test_coverage"]["approved"] is True
    assert reports["simplicity"]["approved"] is True


def test_review_loop_self_heals_and_converges_on_round_two(review_client: TestClient) -> None:
    chat_id = "chat_review_test_02"
    buggy_diff = """
    def fetch_data():
        pass
    """

    # 1. Round 1 starts with stub & missing tests -> in_review
    start_payload = {
        "session_id": chat_id,
        "diff_content": buggy_diff,
        "context_description": "Data fetcher",
        "max_rounds": 3,
    }
    resp_start = review_client.post(f"/chats/{chat_id}/review-loops/start", json=start_payload)
    assert resp_start.status_code == 200
    data_1 = resp_start.json()["data"]
    loop_id = data_1["loop_id"]

    assert data_1["status"] == "in_review"
    assert data_1["is_clean"] is False
    assert data_1["current_round"] == 1
    assert data_1["rounds"][0]["has_blocking_issues"] is True

    # 2. Advance to Round 2 with remediated diff and tests
    fixed_diff = """
    def fetch_data() -> str:
        return "data_payload"

    def test_fetch_data():
        assert fetch_data() == "data_payload"
    """
    advance_payload = {
        "fixed_diff": fixed_diff,
        "fix_note": "Replaced stub pass with concrete return and added unit tests",
    }
    resp_adv = review_client.post(
        f"/chats/{chat_id}/review-loops/{loop_id}/advance",
        json=advance_payload,
    )
    assert resp_adv.status_code == 200
    data_2 = resp_adv.json()["data"]

    assert data_2["status"] == "converged"
    assert data_2["is_clean"] is True
    assert data_2["current_round"] == 2
    assert data_2["rounds"][1]["converged"] is True
    assert data_2["rounds"][1]["has_blocking_issues"] is False
    assert "Replaced stub pass" in (data_2["rounds"][1]["fix_description"] or "")


def test_review_loop_terminates_at_max_rounds_bound(review_client: TestClient) -> None:
    chat_id = "chat_review_test_03"
    unfixed_diff = """
    def stub():
        pass
    """

    # Start loop with max_rounds = 2
    resp_start = review_client.post(
        f"/chats/{chat_id}/review-loops/start",
        json={"session_id": chat_id, "diff_content": unfixed_diff, "max_rounds": 2},
    )
    assert resp_start.status_code == 200
    loop_id = resp_start.json()["data"]["loop_id"]

    # Advance to Round 2 with still-broken diff
    resp_adv = review_client.post(
        f"/chats/{chat_id}/review-loops/{loop_id}/advance",
        json={"fixed_diff": unfixed_diff, "fix_note": "Unsuccessful repair attempt"},
    )
    assert resp_adv.status_code == 200
    data_final = resp_adv.json()["data"]

    # Bounded termination: stopped strictly at max_rounds=2
    assert data_final["status"] == "max_rounds_reached"
    assert data_final["is_clean"] is False
    assert data_final["current_round"] == 2
    assert data_final["max_rounds"] == 2


def test_review_loop_query_and_cleanup(review_client: TestClient) -> None:
    chat_id = "chat_review_test_04"
    clean_diff = "def ok(): return True\ndef test_ok(): assert ok()"

    resp_start = review_client.post(
        f"/chats/{chat_id}/review-loops/start",
        json={"session_id": chat_id, "diff_content": clean_diff, "max_rounds": 3},
    )
    loop_id = resp_start.json()["data"]["loop_id"]

    # 1. Fetch individual loop
    resp_get = review_client.get(f"/chats/{chat_id}/review-loops/{loop_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["data"]["loop_id"] == loop_id

    # 2. List loops
    resp_list = review_client.get(f"/chats/{chat_id}/review-loops")
    assert resp_list.status_code == 200
    assert resp_list.json()["data"]["total_count"] == 1

    # 3. Cleanup
    resp_del = review_client.delete(f"/chats/{chat_id}/review-loops")
    assert resp_del.status_code == 200
    assert resp_del.json()["data"]["cleaned"] is True

    # 4. List after cleanup
    resp_after = review_client.get(f"/chats/{chat_id}/review-loops")
    assert resp_after.status_code == 200
    assert resp_after.json()["data"]["total_count"] == 0
