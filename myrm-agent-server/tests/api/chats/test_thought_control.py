"""Integration and unit tests for CoT stop-thinking control endpoint.

[INPUT]
- httpx, ASGITransport
- app.api.chats.chat.thought_control::{router, is_thought_stopped, clear_thought_signal}

[OUTPUT]
- Pytest test cases verifying stop thinking signal injection and state querying.

[POS]
- tests/api/chats/test_thought_control.py — 思考链收敛与控制 API 单元测试。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.chats.chat.thought_control import (
    clear_thought_signal,
    is_thought_stopped,
)
from app.api.chats.chat.thought_control import (
    router as thought_control_router,
)

test_app = FastAPI()
test_app.include_router(thought_control_router, prefix="/api/v1/chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_stop_thinking_endpoint_triggers_signal(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test_chat_{uuid.uuid4().hex[:8]}"

    try:
        assert not is_thought_stopped(chat_id)

        # Trigger stop thinking without body (default reason)
        resp = await async_client.post(f"/api/v1/chats/{chat_id}/stop-thinking")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["chat_id"] == chat_id
        assert is_thought_stopped(chat_id)

        # Trigger stop thinking with custom reason
        custom_payload = {
            "reason": "runaway_loop_detected",
            "force_immediate_answer": True,
        }
        resp2 = await async_client.post(
            f"/api/v1/chats/{chat_id}/stop-thinking",
            json=custom_payload,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] is True
        assert is_thought_stopped(chat_id)
    finally:
        clear_thought_signal(chat_id)
        assert not is_thought_stopped(chat_id)
