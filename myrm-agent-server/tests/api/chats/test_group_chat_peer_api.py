"""Unit tests for Bot Mode Group Chat and Hermes Peer Messaging endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.chats.group_chat_router

[OUTPUT]
- Pytest test cases covering multi-bot rooms, @-mention dispatch, and peer DM archiving

[POS]
tests/api/chats/test_group_chat_peer_api.py: Comprehensive test suite for group chat endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.chats.group_chat_router import router as group_chat_router


@pytest.fixture
def group_client() -> TestClient:
    """Provide isolated TestClient mounting group_chat_router."""
    app = FastAPI()
    app.include_router(group_chat_router, prefix="/api/v1")
    return TestClient(app)


def test_list_group_rooms(group_client: TestClient) -> None:
    """Verify GET /api/v1/group-chat/rooms returns initialized default room."""
    res = group_client.get("/api/v1/group-chat/rooms")
    assert res.status_code == 200
    rooms = res.json()
    assert isinstance(rooms, list)
    assert len(rooms) >= 1

    default_room = rooms[0]
    assert "room_id" in default_room
    assert default_room["name"] == "Engineering War Room"
    participant_ids = [p["participant_id"] for p in default_room["participants"]]
    assert "user_me" in participant_ids
    assert "code_architect" in participant_ids


def test_create_and_get_group_room(group_client: TestClient) -> None:
    """Verify POST and GET /api/v1/group-chat/rooms."""
    create_payload = {
        "name": "Design & UX Swarm",
        "topic": "Frontend component consistency and accessibility review",
        "initial_agent_ids": ["frontend_lead", "a11y_auditor"],
    }
    create_res = group_client.post("/api/v1/group-chat/rooms", json=create_payload)
    assert create_res.status_code == 201
    room = create_res.json()

    room_id = room["room_id"]
    assert room["name"] == "Design & UX Swarm"
    assert len(room["participants"]) == 3  # user_me + 2 bots

    # Check deterministic avatar properties
    bot_participant = next(p for p in room["participants"] if p["participant_id"] == "frontend_lead")
    assert bot_participant["avatar_color"].startswith("#")
    assert bot_participant["is_avatar_locked"] is True

    # Retrieve specific room
    get_res = group_client.get(f"/api/v1/group-chat/rooms/{room_id}")
    assert get_res.status_code == 200
    assert get_res.json()["room_id"] == room_id

    # 404 for unknown room
    not_found_res = group_client.get("/api/v1/group-chat/rooms/non_existent_room_999")
    assert not_found_res.status_code == 404


def test_post_message_with_mentions(group_client: TestClient) -> None:
    """Verify POST /api/v1/group-chat/rooms/{room_id}/messages triggers bot relays."""
    # Create room
    create_payload = {
        "name": "Triage Channel",
        "topic": "Urgent incident response",
        "initial_agent_ids": ["devops_bot", "security_bot"],
    }
    create_res = group_client.post("/api/v1/group-chat/rooms", json=create_payload)
    room_id = create_res.json()["room_id"]

    # Send message mentioning devops_bot
    msg_payload = {
        "sender_id": "user_me",
        "content": "Please inspect staging deployment health @devops_bot",
        "mentioned_agent_ids": ["devops_bot"],
    }
    post_res = group_client.post(f"/api/v1/group-chat/rooms/{room_id}/messages", json=msg_payload)
    assert post_res.status_code == 200
    dispatched = post_res.json()

    # Expect 2 messages: 1 user prompt + 1 bot acknowledgement relay
    assert len(dispatched) == 2
    assert dispatched[0]["sender_role"] == "human"
    assert dispatched[0]["content"] == msg_payload["content"]

    bot_reply = dispatched[1]
    assert bot_reply["sender_role"] == "assistant_bot"
    assert bot_reply["sender_id"] == "devops_bot"
    assert "Acknowledged instruction" in bot_reply["content"]


def test_peer_direct_message_and_canonical_archive(group_client: TestClient) -> None:
    """Verify Hermes peer consultation and archiving into canonical bot chat."""
    peer_payload = {
        "sender_agent_id": "planner_agent",
        "target_agent_id": "coder_agent",
        "content": "Can you provide the schema for UserProfile?",
        "context_task_id": "task_peer_001",
    }
    res = group_client.post("/api/v1/group-chat/peer/direct-message", json=peer_payload)
    assert res.status_code == 200
    data = res.json()

    assert data["peer_message_id"].startswith("peer_")
    assert data["sender_agent_id"] == "planner_agent"
    assert data["target_agent_id"] == "coder_agent"
    assert "UserProfile" in data["query_content"]
    assert "Verified prerequisite task" in data["reply_content"]
    assert data["canonical_chat_id"] == "canon_planner_agent_coder_agent"
    assert data["latency_ms"] >= 0

    # Verify canonical archives retrieval for target agent
    archives_res = group_client.get("/api/v1/group-chat/peer/archives/coder_agent")
    assert archives_res.status_code == 200
    archives = archives_res.json()
    assert isinstance(archives, list)
    assert len(archives) >= 1

    matched = next((a for a in archives if a["canonical_chat_id"] == data["canonical_chat_id"]), None)
    assert matched is not None
    assert matched["message_count"] >= 2
