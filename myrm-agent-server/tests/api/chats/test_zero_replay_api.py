"""Integration and unit tests for Atomic Snapshot and Live Stream Zero-Replay Reconnect Protocol API.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.zero_replay::router

[OUTPUT]
- Pytest test cases verifying snapshot compilation, handshake verification, and zero-replay filtering.

[POS]
Server-side integration test suite for Item 36 P0. Strictly under 200 lines. Zero `Any`.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.zero_replay import router as zero_replay_router

test_app = FastAPI()
test_app.include_router(zero_replay_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_atomic_snapshot_retrieval_and_state_updates(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    # 1. Fetch initial atomic snapshot
    resp = await async_client.get(f"/api/v1/chats/{chat_id}/atomic-snapshot")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == chat_id
    assert data["state_version"] >= 1
    assert data["status"] == "idle"
    assert data["message_count"] == 0
    assert len(data["epoch_id"]) > 0

    # 2. Update snapshot state with active tools and running status
    patch_req = {
        "status": "running",
        "leaf_entry_id": "entry_node_42",
        "active_tool_calls": [{"id": "call_1", "tool_name": "web_search"}],
        "message_count": 5,
        "latest_turn_summary": "Searching web documentation",
    }
    update_resp = await async_client.post(f"/api/v1/chats/{chat_id}/snapshot-state", json=patch_req)
    assert update_resp.status_code == 200
    updated_data = update_resp.json()["data"]
    assert updated_data["status"] == "running"
    assert updated_data["leaf_entry_id"] == "entry_node_42"
    assert updated_data["state_version"] > data["state_version"]
    assert len(updated_data["active_tool_calls"]) == 1
    assert updated_data["latest_turn_summary"] == "Searching web documentation"

    # 3. Subsequent snapshot fetch matches latest updated state
    fetch_again = await async_client.get(f"/api/v1/chats/{chat_id}/atomic-snapshot")
    assert fetch_again.status_code == 200
    current = fetch_again.json()["data"]
    assert current["state_version"] == updated_data["state_version"]
    assert current["status"] == "running"


@pytest.mark.asyncio
async def test_handshake_stale_epoch_rejection(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    # Stale epoch must trigger handshake_failed
    stale_params = {
        "client_epoch": "stale_epoch_xyz",
        "client_version": 1,
        "client_timestamp_ms": time.time() * 1000.0,
    }
    resp = await async_client.get(f"/api/v1/chats/{chat_id}/live-stream", params=stale_params)
    assert resp.status_code == 200
    body = resp.text
    assert "event: handshake_failed" in body
    assert "require_full_snapshot_reload" in body


@pytest.mark.asyncio
async def test_handshake_success_and_live_ready_subscription(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    # First get current valid snapshot
    snap_resp = await async_client.get(f"/api/v1/chats/{chat_id}/atomic-snapshot")
    snap_data = snap_resp.json()["data"]
    current_epoch = snap_data["epoch_id"]
    current_version = snap_data["state_version"]
    now_ms = snap_data["snapshot_timestamp_ms"]

    valid_params = {
        "client_epoch": current_epoch,
        "client_version": current_version,
        "client_timestamp_ms": now_ms,
    }
    resp = await async_client.get(f"/api/v1/chats/{chat_id}/live-stream", params=valid_params)
    assert resp.status_code == 200
    body = resp.text
    assert "event: live_ready" in body
    assert "connected" in body
    assert "zero_replay_active" in body


@pytest.mark.asyncio
async def test_broadcast_live_event_increments_version(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    snap_before = (await async_client.get(f"/api/v1/chats/{chat_id}/atomic-snapshot")).json()["data"]
    version_before = snap_before["state_version"]

    event_req = {
        "event_type": "tool_heartbeat",
        "payload": {"step": "executing_sql"},
    }
    broadcast_resp = await async_client.post(f"/api/v1/chats/{chat_id}/live-event", json=event_req)
    assert broadcast_resp.status_code == 200
    event_data = broadcast_resp.json()["data"]
    assert event_data["event_type"] == "tool_heartbeat"
    assert event_data["state_version"] > version_before
    assert event_data["session_id"] == chat_id
