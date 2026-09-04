"""Unit tests for chat session overlays endpoints.

[INPUT]
- SessionOverlayManager with active overlays

[OUTPUT]
- GET /{session_id}/overlays returns formatted active overlays
- POST /{session_id}/overlays/{overlay_id}/rollback updates status
"""

import pytest
from fastapi.testclient import TestClient

from myrm_agent_harness.agent.session_overlay.manager import (
    get_session_overlay_manager,
)
from myrm_agent_harness.agent.session_overlay.schema import (
    OverlayScope,
    OverlayStatus,
    OverlayTargetType,
    SessionOverlay,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_get_and_rollback_session_overlays(client: TestClient) -> None:
    session_id = "test-chat-overlay-session"
    mgr = get_session_overlay_manager(session_id)

    ovl = SessionOverlay(
        overlay_id="ovl-api-1",
        scope=OverlayScope.SESSION,
        target_type=OverlayTargetType.TEMP_SKILL_VARIANT,
        target_name="test_tool",
        patch_payload={"strip_params": ["bad_arg"], "advisory_instruction": "Auto-stripped bad_arg"},
        ttl_turns=4,
        status=OverlayStatus.ACTIVE,
    )
    mgr.register_overlay(ovl)

    # 1. Query active overlays
    resp = client.get(f"/api/v1/chats/{session_id}/overlays")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["overlayId"] == "ovl-api-1"
    assert data[0]["remainingTurns"] == 4
    assert data[0]["shellType"] == "skill_variant"
    assert data[0]["advisoryText"] == "Auto-stripped bad_arg"

    # 2. Rollback active overlay
    rb_resp = client.post(f"/api/v1/chats/{session_id}/overlays/ovl-api-1/rollback")
    assert rb_resp.status_code == 200
    assert rb_resp.json()["data"]["rolled_back"] is True

    # 3. Query again: active list should now be empty
    resp2 = client.get(f"/api/v1/chats/{session_id}/overlays")
    assert resp2.status_code == 200
    assert len(resp2.json()["data"]) == 0
