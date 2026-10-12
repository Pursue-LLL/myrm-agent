"""Integration tests for Extension UI reverse push interaction API endpoints:
- GET /api/v1/chats/{chat_id}/ui-requests
- POST /api/v1/chats/{chat_id}/ui-response/{request_id}
- POST /api/v1/chats/{chat_id}/ui-cancel/{request_id}

[INPUT]
- httpx from httpx
- build_minimal_app from tests.support.minimal_app
- get_ui_request_manager from app.services.ui_interaction
- ReversePushUIContext, UISelectOption from myrm_agent_harness.agent.ui

[OUTPUT]
- Pytest integration tests for Extension UI reverse push handshake

[POS]
Server-side integration test suite for Item 28 TransportAgnosticUIContextAndReversePushSubProtocol.
File length < 200 lines. Zero `Any`.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from httpx import ASGITransport
from myrm_agent_harness.agent.ui import ReversePushUIContext, UIRequest, UISelectOption

from app.services.ui_interaction import get_ui_request_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_ui_interaction_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test-ui-{uuid.uuid4().hex[:12]}"
    manager = get_ui_request_manager()

    dispatched: list[UIRequest] = []

    async def mock_push_sink(req: UIRequest) -> None:
        dispatched.append(req)
        await manager.record_request(chat_id, req, context)

    context = ReversePushUIContext(push_sink=mock_push_sink)
    await manager.register_context(chat_id, context)

    try:
        # 1. No pending requests initially
        empty_res = await async_client.get(f"/api/v1/chats/{chat_id}/ui-requests")
        assert empty_res.status_code == 200
        assert empty_res.json()["data"]["count"] == 0

        # 2. Trigger an interactive select prompt asynchronously
        options = [
            UISelectOption(label="Deploy Production", value="prod"),
            UISelectOption(label="Deploy Staging", value="staging"),
        ]

        async def run_select() -> str:
            return await context.select("Choose Target", options, default="staging", timeout_s=10.0)

        select_task = asyncio.create_task(run_select())

        # Give small tick for request to be pushed & recorded
        await asyncio.sleep(0.05)
        assert len(dispatched) == 1
        req_id = dispatched[0].request_id

        # 3. GET /ui-requests should now return the pending request
        pending_res = await async_client.get(f"/api/v1/chats/{chat_id}/ui-requests")
        assert pending_res.status_code == 200
        data = pending_res.json()["data"]
        assert data["count"] == 1
        assert data["requests"][0]["request_id"] == req_id
        assert data["requests"][0]["request_type"] == "select"
        assert data["requests"][0]["title"] == "Choose Target"

        # 4. POST /ui-response/{request_id} resolves the prompt
        submit_res = await async_client.post(
            f"/api/v1/chats/{chat_id}/ui-response/{req_id}",
            json={"value": "prod", "cancelled": False},
        )
        assert submit_res.status_code == 200
        assert submit_res.json()["data"]["resolved"] is True

        # Wait for task completion
        selected_val = await select_task
        assert selected_val == "prod"

        # 5. Check pending requests is cleared
        cleared_res = await async_client.get(f"/api/v1/chats/{chat_id}/ui-requests")
        assert cleared_res.status_code == 200
        assert cleared_res.json()["data"]["count"] == 0

        # 6. Resolving an already completed or unknown request returns 404
        unknown_res = await async_client.post(
            f"/api/v1/chats/{chat_id}/ui-response/unknown_id",
            json={"value": "foo"},
        )
        assert unknown_res.status_code == 404
    finally:
        await manager.unregister_context(chat_id)


@pytest.mark.asyncio
async def test_ui_interaction_api_cancel(async_client: httpx.AsyncClient) -> None:
    chat_id = f"test-ui-cancel-{uuid.uuid4().hex[:12]}"
    manager = get_ui_request_manager()

    dispatched: list[UIRequest] = []

    async def mock_push_sink(req: UIRequest) -> None:
        dispatched.append(req)
        await manager.record_request(chat_id, req, context)

    context = ReversePushUIContext(push_sink=mock_push_sink)
    await manager.register_context(chat_id, context)

    try:
        # Trigger an interactive confirm prompt
        async def run_confirm() -> bool:
            return await context.confirm("Confirm Action", "Do you want to proceed?", timeout_s=10.0)

        confirm_task = asyncio.create_task(run_confirm())
        await asyncio.sleep(0.05)
        assert len(dispatched) == 1
        req_id = dispatched[0].request_id

        # Cancel the request via POST /ui-cancel/{request_id}
        cancel_res = await async_client.post(
            f"/api/v1/chats/{chat_id}/ui-cancel/{req_id}",
            json={"reason": "User dismissed dialog"},
        )
        assert cancel_res.status_code == 200
        assert cancel_res.json()["data"]["cancelled"] is True

        # The context task should raise ExtensionUICancelledException
        with pytest.raises(Exception) as exc_info:
            await confirm_task
        assert "User dismissed dialog" in str(exc_info.value)
    finally:
        await manager.unregister_context(chat_id)
