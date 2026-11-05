"""Integration and unit tests for Embeddable Agent Widget & Host Context Bridge API.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.embed_bridge::router

[OUTPUT]
- Pytest test cases verifying origin enforcement, context injection, security policies, and snippet generation.

[POS]
Server-side integration test suite for Item 41 P1. Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.embed_bridge import router as embed_bridge_router

test_app = FastAPI()
test_app.include_router(embed_bridge_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_session_policy_and_origin_verification(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Set strict policy for chat session
    policy_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/embed/policy",
        json={
            "allowed_origins": ["https://mycorp.com", "*.corp.internal"],
            "allow_form_capture": True,
            "allow_selection_capture": True,
        },
    )
    assert policy_resp.status_code == 200
    assert policy_resp.json()["data"]["allowed_origins"] == ["https://mycorp.com", "*.corp.internal"]

    get_resp = await async_client.get(f"/api/v1/chats/{chat_id}/embed/policy")
    assert get_resp.json()["data"]["allowed_origins"] == ["https://mycorp.com", "*.corp.internal"]

    async def inject_from(origin: str) -> dict[str, object]:
        resp = await async_client.post(
            f"/api/v1/chats/{chat_id}/embed/inject-context",
            json={"origin": origin, "current_url": f"{origin}/page"},
        )
        assert resp.status_code == 200
        payload: dict[str, object] = resp.json()
        return payload

    # Exact origin and subdomain wildcard are allowed
    assert (await inject_from("https://mycorp.com"))["code"] == 0
    assert (await inject_from("https://crm.corp.internal"))["code"] == 0

    # Unauthorized origin is rejected
    assert (await inject_from("https://unauthorized.evil"))["code"] == 403


@pytest.mark.asyncio
async def test_inject_host_context(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Inject context under permissive default policy
    inject_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/embed/inject-context",
        json={
            "origin": "https://portal.example.com",
            "current_url": "https://portal.example.com/checkout/step-2",
            "page_title": "Order Review - Portal",
            "selected_text": "SKU-99201 High-Speed Router",
            "form_fields": {"billing_tier": "enterprise", "coupon": "DISCOUNT50"},
            "user_metadata": {"user_id": "u_8842"},
        },
    )
    assert inject_resp.status_code == 200
    data = inject_resp.json()["data"]
    assert data["session_id"] == chat_id
    assert "@host_context: External Host Webpage Snapshot" in data["context_text"]
    assert "SKU-99201 High-Speed Router" in data["context_text"]
    assert "coupon: DISCOUNT50" in data["context_text"]


@pytest.mark.asyncio
async def test_inject_host_context_forbidden(async_client: httpx.AsyncClient) -> None:
    chat_id = f"chat_{uuid.uuid4().hex[:8]}"

    # Restrict policy
    await async_client.post(
        f"/api/v1/chats/{chat_id}/embed/policy",
        json={"allowed_origins": ["https://safe-domain.org"]},
    )

    # Try injecting from forbidden origin
    inject_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/embed/inject-context",
        json={
            "origin": "https://attacker.org",
            "current_url": "https://attacker.org/phishing",
        },
    )
    assert inject_resp.status_code == 200  # returns standard error JSON with code 403
    payload = inject_resp.json()
    assert payload["code"] == 403
    assert "not permitted by embed security policy" in payload["message"]


@pytest.mark.asyncio
async def test_generate_embed_snippet(async_client: httpx.AsyncClient) -> None:
    chat_id = "chat_test_widget"
    resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/embed/generate-snippet",
        json={
            "base_url": "https://agent.myrm.io",
            "mode": "slideout_drawer",
            "theme": "dark",
            "allowed_origin": "https://host.corp",
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "slideout_drawer"
    assert 'data-chat-id="chat_test_widget"' in data["snippet"]
    assert 'src="https://agent.myrm.io/widget/loader.js"' in data["snippet"]
    assert 'data-mode="slideout_drawer"' in data["snippet"]
    assert 'data-theme="dark"' in data["snippet"]
