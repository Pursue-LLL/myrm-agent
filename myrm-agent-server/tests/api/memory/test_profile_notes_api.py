"""Integration tests for Dual-Layer Profile & Working Notes API endpoints.

[INPUT]
- fastapi.testclient::TestClient
- app.main::app

[OUTPUT]
- Pytest cases verifying intake noise filtration, capacity watermarks, and CRUD endpoints

[POS]
Server-side integration testing for Hermes-grade memory purity and capacity budgeting.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.profile_notes_router import router as profile_notes_router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(profile_notes_router, prefix="/api/memory")
    with TestClient(app) as test_client:
        yield test_client


def test_profile_notes_intake_filter_reject_progress(client: TestClient) -> None:
    response = client.post(
        "/api/memory/profile-notes/intake-check",
        json={"content": "Phase 3 completed and all tests passed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert not data["accepted"]
    assert data["garbage_category"] == "task_progress"
    assert data["rejected_reason"] is not None


def test_profile_notes_intake_filter_reject_ephemeral_pr(client: TestClient) -> None:
    response = client.post(
        "/api/memory/profile-notes/intake-check",
        json={"content": "Please review PR #1234 before deploying"},
    )
    assert response.status_code == 200
    data = response.json()
    assert not data["accepted"]
    assert data["garbage_category"] == "ephemeral_number"


def test_profile_notes_intake_filter_accept_user_preference(client: TestClient) -> None:
    response = client.post(
        "/api/memory/profile-notes/intake-check",
        json={"content": "用户代码风格偏好使用 Python PEP8 规范，严禁使用 Any 类型"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["accepted"]
    assert data["target_layer"] == "user"
    assert data["rejected_reason"] is None


def test_profile_notes_watermarks_and_contents_flow(client: TestClient) -> None:
    # 1. Check initial watermarks
    wm_resp = client.get("/api/memory/profile-notes/watermarks")
    assert wm_resp.status_code == 200
    wm_data = wm_resp.json()
    assert "user_watermark" in wm_data
    assert "memory_watermark" in wm_data
    assert wm_data["user_watermark"]["max_chars"] == 1375
    assert wm_data["memory_watermark"]["max_chars"] == 2200

    # 2. Update contents
    update_resp = client.put(
        "/api/memory/profile-notes/contents",
        json={
            "user_content": "User prefers concise responses.",
            "memory_content": "Architecture guideline: single file <= 400 lines.",
        },
    )
    assert update_resp.status_code == 200
    update_data = update_resp.json()
    assert update_data["user_content"] == "User prefers concise responses."
    assert "single file <= 400 lines" in update_data["memory_content"]
    assert update_data["user_watermark"]["current_chars"] > 0
    assert update_data["memory_watermark"]["current_chars"] > 0

    # 3. Retrieve updated contents
    get_resp = client.get("/api/memory/profile-notes/contents")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["user_content"] == "User prefers concise responses."
