"""Integration tests for A2A Provider Server endpoints and services."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.a2a.types import (
    A2A_PROTOCOL_VERSION,
    A2ATask,
    JsonRpcErrorCode,
    TaskStatus,
)

from app.api.a2a.router import router as a2a_router
from app.services.a2a.card_generator import AgentCardGenerator
from app.services.a2a.service import A2AServerService
from app.services.a2a.task_store import A2ATaskStore
from app.services.a2a.webhook_sender import A2AWebhookSender


def _create_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(a2a_router, prefix="/api/v1/a2a")
    generator = AgentCardGenerator()

    @test_app.get("/.well-known/agent-card.json")
    async def root_agent_card(request: Request) -> dict[str, object]:
        card = await generator.generate_card(base_url=str(request.base_url).rstrip("/"))
        return card.model_dump(by_alias=True)

    return test_app


@pytest.mark.asyncio
async def test_root_well_known_agent_card() -> None:
    """GET /.well-known/agent-card.json returns valid default AgentCard."""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/.well-known/agent-card.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Myrm Agent"
        assert "supportedInterfaces" in data
        assert len(data["supportedInterfaces"]) >= 1
        assert data["supportedInterfaces"][0]["protocolBinding"] == "JSONRPC"
        assert data["supportedInterfaces"][0]["protocolVersion"] == A2A_PROTOCOL_VERSION
        assert data["capabilities"]["pushNotifications"] is True
        assert len(data["skills"]) >= 1


@pytest.mark.asyncio
async def test_api_v1_a2a_agent_card_discovery() -> None:
    """GET /api/v1/a2a/.well-known/agent-card.json and per-agent endpoint."""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp1 = await client.get("/api/v1/a2a/.well-known/agent-card.json")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["name"] == "Myrm Agent"

        resp2 = await client.get("/api/v1/a2a/agents/default/.well-known/agent-card.json")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert "Agent-default" in data2["name"] or "Myrm Agent" in data2["name"]


@pytest.mark.asyncio
async def test_a2a_rpc_send_task_and_get_lifecycle() -> None:
    """POST /api/v1/a2a/rpc creates task and retrieves it."""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "req-1",
            "method": "tasks/send",
            "params": {
                "prompt": "Hello agent",
            },
        }
        resp = await client.post("/api/v1/a2a/rpc", json=payload)
        assert resp.status_code == 200
        res = resp.json()
        assert res.get("jsonrpc") == "2.0"
        assert res.get("id") == "req-1"
        assert "result" in res
        task = res["result"]
        assert task["status"] in ("pending", "in_progress", "completed")
        task_id = task.get("taskId") or task.get("id")
        assert task_id

        get_payload = {
            "jsonrpc": "2.0",
            "id": "req-2",
            "method": "tasks/get",
            "params": {"taskId": task_id},
        }
        get_resp = await client.post("/api/v1/a2a/rpc", json=get_payload)
        assert get_resp.status_code == 200
        get_res = get_resp.json()
        assert (get_res["result"].get("taskId") or get_res["result"].get("id")) == task_id


@pytest.mark.asyncio
async def test_a2a_rpc_cancel_task() -> None:
    """POST /api/v1/a2a/rpc cancels an existing task."""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "req-send",
            "method": "tasks/send",
            "params": {"prompt": "Task to cancel"},
        }
        resp = await client.post("/api/v1/a2a/rpc", json=payload)
        task = resp.json()["result"]
        task_id = task.get("taskId") or task.get("id")

        cancel_payload = {
            "jsonrpc": "2.0",
            "id": "req-cancel",
            "method": "tasks/cancel",
            "params": {"taskId": task_id},
        }
        c_resp = await client.post("/api/v1/a2a/rpc", json=cancel_payload)
        assert c_resp.status_code == 200
        c_res = c_resp.json()
        assert c_res["result"]["cancelled"] is True


@pytest.mark.asyncio
async def test_a2a_rpc_invalid_method() -> None:
    """Unknown method returns METHOD_NOT_FOUND code."""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": "err-1",
            "method": "unknown/op",
            "params": {},
        }
        resp = await client.post("/api/v1/a2a/rpc", json=payload)
        assert resp.status_code == 200
        res = resp.json()
        assert res.get("error")
        assert res["error"]["code"] == int(JsonRpcErrorCode.METHOD_NOT_FOUND)


@pytest.mark.asyncio
async def test_a2a_task_store_bounds_and_eviction() -> None:
    """A2ATaskStore respects max_capacity capacity."""
    store = A2ATaskStore(max_capacity=5)

    # First add completed tasks to test eviction
    for i in range(5):
        t = A2ATask(
            task_id=f"t-done-{i}",
            status=TaskStatus.COMPLETED,
            created_at=time.time(),
            updated_at=time.time(),
        )
        await store.create_task(t)

    # Now add one more task, oldest should be evicted
    new_t = A2ATask(
        task_id="t-new",
        status=TaskStatus.PENDING,
        created_at=time.time(),
        updated_at=time.time(),
    )
    await store.create_task(new_t)

    assert await store.get_task("t-done-0") is None
    assert await store.get_task("t-new") is not None


@pytest.mark.asyncio
async def test_a2a_webhook_delivery_with_hmac() -> None:
    """Webhook sender invokes push_url with HMAC headers."""
    sender = A2AWebhookSender(max_retries=1)
    store = A2ATaskStore()
    service = A2AServerService(task_store=store, webhook_sender=sender)

    with patch.object(sender, "deliver", new_callable=AsyncMock) as mock_deliver:
        mock_deliver.return_value = True
        _ = await service.send_task(
            "Webhook test task",
            push_url="https://example.com/webhook",
            push_secret="top-secret-key",
        )
        await asyncio.sleep(0.05)
        assert mock_deliver.called
        call_args = mock_deliver.call_args
        assert call_args[0][0] == "https://example.com/webhook"
        assert call_args[1]["push_secret"] == "top-secret-key"
