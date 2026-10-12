"""
[INPUT]
- TestClient from starlette/fastapi test suite
- Self-evolution API routes under /api/v1/self-evolution

[OUTPUT]
- Unit tests verifying self-evolution locate AST search, task creation, line numbers, listing, and recovery rollback

[POS]
Unit tests for Designer's Eye UI Element Inspector and Self-Evolution Pipeline backend API.
Strict typing: Zero `Any`. File length < 160 lines.
"""

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.self_evolution.routes import router as self_evolution_router


@pytest.fixture
def evolution_client() -> TestClient:
    app = FastAPI()
    app.include_router(self_evolution_router, prefix="/api/v1/self-evolution")
    return TestClient(app)


def test_locate_component_source(evolution_client: TestClient):
    """Test resolving candidate component source files from DOM signals."""
    payload = {
        "dom_selector": "#chat-window-container > div.composer",
        "tag_name": "div",
        "classes": ["chat-box", "composer", "rounded-xl"],
        "component_hint": "ChatWindow",
        "component_hierarchy": ["ChatLayout", "AppShell"],
        "text_snippet": "Type a message...",
    }

    response = evolution_client.post("/api/v1/self-evolution/locate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "candidates" in data
    assert len(data["candidates"]) >= 1
    assert data["matched_file"] == "src/components/features/chatwindow/ChatWindow.tsx"
    assert data["confidence"] == "hint_inferred"


def test_create_self_evolution_task_with_primary_source(evolution_client: TestClient):
    """Test submitting feedback with precisely identified primary source location and line number."""
    payload = {
        "dom_selector": "button.send-btn",
        "tag_name": "button",
        "classes": ["send-btn", "bg-primary"],
        "component_hint": "SendButton",
        "primary_source": {
            "file_name": "src/components/features/chat/SendButton.tsx",
            "line_number": 42,
            "column_number": 10,
            "component_name": "SendButton",
            "confidence": "fiber_debug",
        },
        "user_prompt": "Increase button elevation and padding to px-4 py-2",
        "preset_tags": ["spacing", "border_radius"],
    }

    response = evolution_client.post("/api/v1/self-evolution/tasks", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["task_id"].startswith("evo-")
    assert data["status"] == "verified"
    assert data["target_component_file"] == "src/components/features/chat/SendButton.tsx"
    assert data["target_line_number"] == 42
    assert "src/components/features/chat/SendButton.tsx:42" in data["diff_summary"]
    assert data["recoverable_checkpoint_id"].startswith("chk-")


def test_create_self_evolution_task(evolution_client: TestClient):
    """Test submitting element inspection feedback to generate a self-evolution task."""
    payload = {
        "dom_selector": "#mobile-hub-container > div.active-sessions-card",
        "tag_name": "div",
        "classes": ["active-sessions-card", "rounded-2xl", "bg-card"],
        "component_hint": "features/mobile/MobileSessionHub",
        "user_prompt": "Adjust card padding to p-5 and ensure dark-mode contrast aligns with design system",
        "preset_tags": ["dark_mode", "spacing"],
        "computed_style_summary": {
            "padding": "16px",
            "backgroundColor": "rgb(255, 255, 255)",
        },
    }

    response = evolution_client.post("/api/v1/self-evolution/tasks", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["task_id"].startswith("evo-")
    assert data["status"] == "verified"
    assert data["dom_selector"] == payload["dom_selector"]
    assert data["tag_name"] == "div"
    assert data["target_component_file"] == "src/components/features/mobile/MobileSessionHub.tsx"
    assert data["recoverable_checkpoint_id"].startswith("chk-")
    assert "created_at" in data


def test_list_self_evolution_tasks(evolution_client: TestClient):
    """Test retrieving history of self-evolution tasks."""
    response = evolution_client.get("/api/v1/self-evolution/tasks")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_recover_self_evolution_with_checkpoint(evolution_client: TestClient):
    """Test rolling back to a specific checkpoint id."""
    payload = {
        "dom_selector": ".chat-composer-box",
        "tag_name": "textarea",
        "classes": ["chat-composer-box"],
        "user_prompt": "Make text input responsive to dynamic height",
    }
    create_res = evolution_client.post("/api/v1/self-evolution/tasks", json=payload)
    assert create_res.status_code == 201
    created_task = create_res.json()
    chk_id = created_task["recoverable_checkpoint_id"]

    recover_res = evolution_client.post("/api/v1/self-evolution/recover", json={"checkpoint_id": chk_id})
    assert recover_res.status_code == 200
    rec_data = recover_res.json()
    assert rec_data["success"] is True
    assert rec_data["restored_checkpoint_id"] == chk_id


def test_recover_nonexistent_checkpoint_404(evolution_client: TestClient):
    """Test rolling back to an invalid checkpoint raises 404."""
    recover_res = evolution_client.post(
        "/api/v1/self-evolution/recover",
        json={"checkpoint_id": "nonexistent_chk_999999"},
    )
    assert recover_res.status_code == 404
