"""Integration and unit tests for memory preference radar service and API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.memory.radar import (
    RadarFeedbackAction,
    RecordImplicitFeedbackRequest,
    UpdatePreferenceRadarRequest,
)
from app.services.memory.preference_radar_service import PreferenceRadarService


@pytest.fixture
def radar_service() -> PreferenceRadarService:
    return PreferenceRadarService()


@pytest.mark.asyncio
async def test_radar_initial_state(radar_service: PreferenceRadarService) -> None:
    session_id = "session-test-01"
    state = await radar_service.get_state(session_id)

    assert state.session_id == session_id
    assert state.recency == 1.0
    assert state.actionability == 1.0
    assert state.technical_depth == 1.0
    assert state.conciseness == 1.0
    assert state.breadth == 1.0
    assert not state.locked
    assert "recency" in state.effective_signal_weights
    assert "importance" in state.effective_signal_weights


@pytest.mark.asyncio
async def test_manual_fine_tuning_and_clamping(radar_service: PreferenceRadarService) -> None:
    session_id = "session-test-02"

    # Test valid boundary tuning
    req = UpdatePreferenceRadarRequest(
        recency=2.2,
        actionability=3.0,  # Max bound
        locked=True,
    )
    state = await radar_service.update_state(session_id, req)

    assert state.recency == 2.2
    assert state.actionability == 3.0
    assert state.locked is True

    from pydantic import ValidationError

    # Ensure out-of-bound is rejected by Pydantic schema validation
    with pytest.raises(ValidationError):
        UpdatePreferenceRadarRequest(actionability=3.5)

    # When locked, implicit feedback should not alter weights
    fb_req = RecordImplicitFeedbackRequest(action=RadarFeedbackAction.MORE_CODE)
    state_after_fb = await radar_service.record_feedback(session_id, fb_req)
    assert state_after_fb.actionability == 3.0


@pytest.mark.asyncio
async def test_implicit_feedback_and_natural_language_heuristic(
    radar_service: PreferenceRadarService,
) -> None:
    session_id = "session-test-03"

    # Natural language asking for code
    req_nl = RecordImplicitFeedbackRequest(
        action=RadarFeedbackAction.POSITIVE_ACCEPT,
        raw_prompt="请直接给出可运行代码，不要啰嗦",
    )
    state = await radar_service.record_feedback(session_id, req_nl)

    # Heuristic should override to MORE_CODE, boosting actionability
    assert state.actionability > 1.0
    assert state.breadth < 1.0


@pytest.mark.asyncio
async def test_reset_to_neutral(radar_service: PreferenceRadarService) -> None:
    session_id = "session-test-04"

    await radar_service.update_state(
        session_id,
        UpdatePreferenceRadarRequest(recency=2.5, conciseness=0.4),
    )

    reset_state = await radar_service.update_state(
        session_id,
        UpdatePreferenceRadarRequest(reset_to_neutral=True),
    )

    assert reset_state.recency == 1.0
    assert reset_state.conciseness == 1.0


@pytest.mark.asyncio
async def test_persistence_and_cold_boot_recovery(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = "session-persistence-01"
    storage_file = str(tmp_path) + "/preference_radar.json"

    monkeypatch.setattr(
        PreferenceRadarService,
        "_resolve_storage_file",
        lambda self: Path(storage_file),
    )

    srv1 = PreferenceRadarService()
    await srv1.update_state(
        session_id,
        UpdatePreferenceRadarRequest(technical_depth=2.8, conciseness=2.5, locked=True),
    )

    assert Path(storage_file).is_file()

    srv2 = PreferenceRadarService()
    state2 = await srv2.get_state(session_id)
    assert state2.technical_depth == 2.8
    assert state2.conciseness == 2.5
    assert state2.locked is True

    weights = srv2.get_effective_signal_weights(session_id)
    assert "importance" in weights
    assert weights["importance"] > 0


@pytest.mark.asyncio
async def test_multi_session_isolation(radar_service: PreferenceRadarService) -> None:
    """Verify session A and session B maintain completely isolated preference states."""
    session_a = "session-iso-a"
    session_b = "session-iso-b"

    await radar_service.update_state(
        session_a,
        UpdatePreferenceRadarRequest(recency=2.6, technical_depth=2.4, locked=True),
    )

    state_b = await radar_service.get_state(session_b)
    assert state_b.recency == 1.0
    assert state_b.technical_depth == 1.0
    assert state_b.locked is False

    state_a = await radar_service.get_state(session_a)
    assert state_a.recency == 2.6
    assert state_a.technical_depth == 2.4
    assert state_a.locked is True


@pytest.mark.asyncio
async def test_concurrent_updates_thread_safety(radar_service: PreferenceRadarService) -> None:
    """Verify concurrent updates from multiple tasks do not corrupt radar state."""
    import asyncio

    session_id = "session-concurrent-01"

    async def update_dim(depth: float) -> None:
        await radar_service.update_state(
            session_id,
            UpdatePreferenceRadarRequest(technical_depth=depth),
        )

    tasks = [update_dim(1.0 + i * 0.1) for i in range(10)]
    await asyncio.gather(*tasks)

    final_state = await radar_service.get_state(session_id)
    assert 1.0 <= final_state.technical_depth <= 3.0


@pytest.mark.asyncio
async def test_corrupted_storage_fallback_graceful(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify corrupt/malformed JSON in storage recovers gracefully to baseline without crashing."""
    storage_file = Path(str(tmp_path) + "/corrupt_radar.json")
    storage_file.write_text("MALFORMED_JSON_CONTENT{{{", encoding="utf-8")

    monkeypatch.setattr(
        PreferenceRadarService,
        "_resolve_storage_file",
        lambda self: storage_file,
    )

    srv = PreferenceRadarService()
    state = await srv.get_state("session-recover-01")
    assert state.recency == 1.0
    assert state.actionability == 1.0
    assert state.locked is False


def test_radar_http_router_endpoints() -> None:
    """End-to-end HTTP contract test verifying API routing and status codes via FastAPI."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.memory.router import router as memory_router

    test_app = FastAPI()
    test_app.include_router(memory_router, prefix="/api/v1/memory")
    client = TestClient(test_app)

    session_id = "http-e2e-session"

    # 1. GET initial state
    resp_get = client.get(f"/api/v1/memory/radar/{session_id}")
    assert resp_get.status_code == 200
    get_json = resp_get.json()
    assert get_json["session_id"] == session_id
    assert get_json["recency"] == 1.0
    assert get_json["locked"] is False

    # 2. POST tune
    resp_tune = client.post(
        f"/api/v1/memory/radar/{session_id}/tune",
        json={"recency": 2.2, "locked": True},
    )
    assert resp_tune.status_code == 200
    tune_json = resp_tune.json()
    assert tune_json["recency"] == 2.2
    assert tune_json["locked"] is True

    # 3. POST feedback (locked -> preserves weights)
    resp_fb = client.post(
        f"/api/v1/memory/radar/{session_id}/feedback",
        json={"action": "more_code", "raw_prompt": "more code"},
    )
    assert resp_fb.status_code == 200
    fb_json = resp_fb.json()
    assert fb_json["recency"] == 2.2



