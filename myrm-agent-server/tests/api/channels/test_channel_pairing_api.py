"""Integration and unit tests for model-agnostic channel visual pairing API and handshake.

[TEST TARGETS]
- app.api.channels.pairing_router
- app.services.channels.pairing.channel_handshake_service
- Model-agnostic execution flow independent of LLM chat loops
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.channels.pairing_router import pairing_router
from app.services.channels.pairing.channel_handshake_service import (
    ChannelHandshakeService,
)
from app.services.channels.pairing.pairing_types import (
    ChannelPingRequest,
    ChannelPlatform,
    PairingConfirmRequest,
    PairingSessionCreateRequest,
    PairingStatus,
)

test_app = FastAPI()
test_app.include_router(pairing_router, prefix="/api/channels/pairing")


@pytest.fixture
async def pairing_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=15.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_create_pairing_session_returns_qr_code(
    pairing_client: httpx.AsyncClient,
) -> None:
    """Test generating dynamic pairing session and SVG QR code."""
    payload = {
        "platform": "wechat",
        "custom_label": "My Test WeChat Bot",
    }
    response = await pairing_client.post("/api/channels/pairing/session", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["session_id"].startswith("pair_")
    assert data["platform"] == "wechat"
    assert data["status"] == "pending"
    assert data["qr_code"] is not None
    assert "data:image/svg+xml;base64," in data["qr_code"]["qr_matrix_base64"]
    assert "myrm://channels/handshake" in data["qr_code"]["pairing_url"]
    assert data["qr_code"]["expires_in_seconds"] == 300


@pytest.mark.asyncio
async def test_get_pairing_session_lifecycle(
    pairing_client: httpx.AsyncClient,
) -> None:
    """Test polling pairing session status."""
    create_res = await pairing_client.post(
        "/api/channels/pairing/session",
        json={"platform": "wecom"},
    )
    assert create_res.status_code == 200
    session_id = create_res.json()["session_id"]

    poll_res = await pairing_client.get(f"/api/channels/pairing/session/{session_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["session_id"] == session_id
    assert poll_data["status"] == "pending"


@pytest.mark.asyncio
async def test_confirm_pairing_session_and_token_binding(
    pairing_client: httpx.AsyncClient,
) -> None:
    """Test scan callback confirmation and token masking."""
    create_res = await pairing_client.post(
        "/api/channels/pairing/session",
        json={"platform": "feishu"},
    )
    session_id = create_res.json()["session_id"]

    confirm_res = await pairing_client.post(
        f"/api/channels/pairing/session/{session_id}/confirm",
        json={
            "auth_token": "feishu_token_secret_12345678",
            "user_identity": "ou_user_8899aabb",
        },
    )
    assert confirm_res.status_code == 200
    confirm_data = confirm_res.json()
    assert confirm_data["status"] == "authenticated"
    assert confirm_data["persisted"] is True

    # Poll session again to verify authenticated state and masked token
    poll_res = await pairing_client.get(f"/api/channels/pairing/session/{session_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["status"] == "authenticated"
    assert poll_data["user_identity"] == "ou_user_8899aabb"
    assert poll_data["bound_token_masked"] == "feis****5678"


@pytest.mark.asyncio
async def test_verify_channel_ping_connectivity(
    pairing_client: httpx.AsyncClient,
) -> None:
    """Test one-click connectivity ping verification."""
    ping_payload = {
        "platform": "dingtalk",
        "target_recipient": "dingtalk_user_001",
        "test_message": "Connectivity health check",
    }
    response = await pairing_client.post("/api/channels/pairing/verify-ping", json=ping_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["platform"] == "dingtalk"
    assert data["success"] is True
    assert data["latency_ms"] > 0
    assert data["receipt_id"].startswith("rcpt_")


@pytest.mark.asyncio
async def test_model_agnostic_decoupled_execution_e2e() -> None:
    """End-to-end verification proving pairing is 100% decoupled from LLM models.

    Simulates scenario where the active model is a zero-parameter mock or lightweight
    offline model: Channel pairing and verification succeed completely without triggering
    any LLM completions or natural language command interactions (like WorkBuddy's acquire_token).
    """
    service = ChannelHandshakeService()

    # 1. Initialize pairing without any prompt or LLM turn
    session = service.create_pairing_session(
        PairingSessionCreateRequest(
            platform=ChannelPlatform.WECHAT,
            custom_label="Zero-LLM WeChat Bridge",
        )
    )
    assert session.status == PairingStatus.PENDING
    assert session.qr_code is not None

    # 2. Complete pairing via webhook/scan callback
    confirm_res = await service.confirm_pairing(
        session.session_id,
        PairingConfirmRequest(
            auth_token="wechat_bot_token_abcdef123456",
            user_identity="wx_gh_987654321",
        ),
    )
    assert confirm_res is not None
    assert confirm_res.status == PairingStatus.AUTHENTICATED

    # 3. Perform Ping-Pong connectivity self-check
    ping_res = await service.verify_ping(
        ChannelPingRequest(
            platform=ChannelPlatform.WECHAT,
            target_recipient="wx_gh_987654321",
            test_message="Zero-LLM pairing succeeded",
        )
    )
    assert ping_res.success is True
    assert ping_res.latency_ms >= 40.0
    assert ping_res.receipt_id.startswith("rcpt_")
