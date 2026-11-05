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
async def test_atomic_snapshot_retrieval_is_stable_per_session(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    resp = await async_client.get(f"/api/v1/chats/{chat_id}/atomic-snapshot")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["session_id"] == chat_id
    assert data["state_version"] >= 1
    assert data["status"] == "idle"
    assert data["message_count"] == 0
    assert data["active_tool_calls"] == []
    assert len(data["epoch_id"]) > 0

    # Nothing reports session state, so a second fetch keeps the epoch and the version
    again = (await async_client.get(f"/api/v1/chats/{chat_id}/atomic-snapshot")).json()["data"]
    assert again["epoch_id"] == data["epoch_id"]
    assert again["state_version"] == data["state_version"]

    # Another session gets its own epoch
    other = (await async_client.get(f"/api/v1/chats/test_chat_{uuid.uuid4().hex[:8]}/atomic-snapshot")).json()["data"]
    assert other["epoch_id"] != data["epoch_id"]


@pytest.mark.asyncio
async def test_handshake_stale_epoch_rejection(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    # Stale epoch must trigger handshake_failed
    stale_params: dict[str, str | int | float] = {
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
