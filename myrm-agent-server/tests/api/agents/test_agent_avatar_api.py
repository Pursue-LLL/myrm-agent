"""Unit tests for Agent Avatar Generation & Dice Lock API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.agents.agent_avatar_router

[OUTPUT]
- Pytest test cases covering deterministic SVG generation, 4 style presets, AI avatar dispatch, and profile avatar locking.

[POS]
tests/api/agents/test_agent_avatar_api.py: Full test suite for agent avatar endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.agent_avatar_router import router as agent_avatar_router


@pytest.fixture
def avatar_client() -> TestClient:
    """Provide isolated TestClient fixture mounting agent_avatar_router."""
    app = FastAPI()
    app.include_router(agent_avatar_router, prefix="/api/v1")
    return TestClient(app)


def test_generate_svg_avatar_beam_api(avatar_client: TestClient) -> None:
    """Verify POST /api/v1/agents/avatar/generate-svg produces valid beam SVG."""
    payload = {
        "seed": "agent-alpha-99",
        "style": "beam",
        "background_color": "#6366f1",
    }
    response = avatar_client.post("/api/v1/agents/avatar/generate-svg", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["seed"] == "agent-alpha-99"
    assert data["style"] == "beam"
    assert "<svg" in data["svg_data"]
    assert "</svg>" in data["svg_data"]
    assert "beam-glow" in data["svg_data"]


def test_generate_svg_avatar_all_styles_api(avatar_client: TestClient) -> None:
    """Verify deterministic SVG generation across all 4 style presets."""
    styles = ["pixel", "cyberpunk", "bauhaus", "beam"]
    for s in styles:
        payload = {
            "seed": f"seed-for-{s}",
            "style": s,
            "background_color": "#10b981",
        }
        res = avatar_client.post("/api/v1/agents/avatar/generate-svg", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "<svg" in data["svg_data"]
        assert "</svg>" in data["svg_data"]


def test_generate_ai_avatar_api(avatar_client: TestClient) -> None:
    """Verify POST /api/v1/agents/avatar/generate-ai returns image URL."""
    payload = {
        "prompt": "Cyberpunk robotic owl with neon eyes",
        "style": "cyberpunk",
    }
    response = avatar_client.post("/api/v1/agents/avatar/generate-ai", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["prompt"] == payload["prompt"]
    assert data["image_url"].startswith("http")


def test_set_and_get_agent_avatar_lock_api(avatar_client: TestClient) -> None:
    """Verify setting, locking, and retrieving an agent avatar."""
    agent_id = "test-agent-dice-007"
    set_payload = {
        "seed": "locked-seed-42",
        "style": "cyberpunk",
        "background_color": "#ec4899",
        "is_locked": True,
        "svg_data": "<svg><rect width='100' height='100' fill='#ec4899'/></svg>",
        "image_url": None,
    }
    set_res = avatar_client.post(f"/api/v1/agents/avatar/{agent_id}", json=set_payload)
    assert set_res.status_code == 200
    set_data = set_res.json()
    assert set_data["is_locked"] is True
    assert set_data["seed"] == "locked-seed-42"
    assert set_data["background_color"] == "#ec4899"

    get_res = avatar_client.get(f"/api/v1/agents/avatar/{agent_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["is_locked"] is True
    assert get_data["seed"] == "locked-seed-42"
    assert get_data["style"] == "cyberpunk"


def test_get_agent_avatar_default_fallback_api(avatar_client: TestClient) -> None:
    """Verify GET on uninitialized agent generates default unlocked avatar."""
    agent_id = "brand-new-agent-xyz"
    get_res = avatar_client.get(f"/api/v1/agents/avatar/{agent_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["is_locked"] is False
    assert get_data["seed"] == agent_id
    assert "<svg" in get_data["svg_data"]
