"""Unit and integration tests for A2A Provider Server endpoints and services."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.a2a.types import (
    A2A_PROTOCOL_VERSION,
    JsonRpcErrorCode,
    TaskStatus,
)

from app.main import app
from app.services.a2a.service import A2AServerService
from app.services.a2a.task_store import A2ATaskStore
from app.services.a2a.webhook_sender import A2AWebhookSender


@pytest.mark.asyncio
async def test_root_well_known_agent_card() -> None:
    """GET /.well-known/agent-card.json returns valid default AgentCard."""
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
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp1 = await client.get("/api/v1/a2a/.well-known/agent-card.json")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["name"] == "Myrm Agent"

        resp2 = await client.get("/api/v1/a2a/agents/coder/.well-known/agent-card.json")
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert "coder" in data2["name"].lower()
        assert "/agents/coder/rpc" in data2["supportedInterfaces"][0]["url"]


@pytest.mark.asyncio
async def test_a2a_rpc_tasks_lifecycle() -> None:
    """POST /api/v1/a2a/rpc handles tasks/send, tasks/get, and tasks/cancel."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Send task
        send_payload = {
            "jsonrpc": "2.0",
            "method": "tasks/send",
            "params": {
                "prompt": "Write a python script to calculate fibonacci",
                "agentId": "coder",
            },
            "id": "req-1",
        }
        resp = await client.post("/api/v1/a2a/rpc", json=send_payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["jsonrpc"] == "2.0"
        assert body["id"] == "req-1"
        assert body["error"] is None
        result = body["result"]
        task_id = result["taskId"]
        assert task_id.startswith("a2a-")
        assert result["status"] in ("pending", "working", "completed")

        # 2. Get task immediately
        get_payload = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {"taskId": task_id},
            "id": "req-2",
        }
        resp_get = await client.post("/api/v1/a2a/rpc", json=get_payload)
        assert resp_get.status_code == 200
        body_get = resp_get.json()
        assert body_get["id"] == "req-2"
        assert body_get["result"]["taskId"] == task_id

        # 3. Wait briefly for background execution to complete
        await asyncio.sleep(0.1)

        resp_get_final = await client.post("/api/v1/a2a/rpc", json=get_payload)
        final_result = resp_get_final.json()["result"]
        assert final_result["status"] == "completed"
        assert len(final_result["messages"]) >= 2  # user prompt + agent response
        assert len(final_result["artifacts"]) >= 1


@pytest.mark.asyncio
async def test_a2a_rpc_error_handling() -> None:
    """JSON-RPC error codes are accurately returned."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid method
        resp1 = await client.post(
            "/api/v1/a2a/rpc",
            json={"jsonrpc": "2.0", "method": "unknown/method", "id": 10},
        )
        assert resp1.status_code == 200
        b1 = resp1.json()
        assert b1["error"]["code"] == int(JsonRpcErrorCode.METHOD_NOT_FOUND)

        # Missing prompt
        resp2 = await client.post(
            "/api/v1/a2a/rpc",
            json={"jsonrpc": "2.0", "method": "tasks/send", "params": {}, "id": 11},
        )
        assert resp2.status_code == 200
        b2 = resp2.json()
        assert b2["error"]["code"] == int(JsonRpcErrorCode.INVALID_PARAMS)

        # Task not found
        resp3 = await client.post(
            "/api/v1/a2a/rpc",
            json={
                "jsonrpc": "2.0",
                "method": "tasks/get",
                "params": {"taskId": "non-existent-task-id"},
                "id": 12,
            },
        )
        assert resp3.status_code == 200
        b3 = resp3.json()
        assert b3["error"]["code"] == int(JsonRpcErrorCode.TASK_NOT_FOUND)


@pytest.mark.asyncio
async def test_a2a_task_store_and_cancellation() -> None:
    """TaskStore handles state transitions and cancellations."""
    store = A2ATaskStore(max_capacity=5)
    service = A2AServerService(task_store=store)

    task = await service.send_task("Compute infinite series")
    assert task.status == TaskStatus.PENDING

    # Attempt to cancel
    cancelled = await service.cancel_task(task.task_id)
    assert cancelled is True

    record = await service.get_task(task.task_id)
    assert record is not None
    assert record.status == TaskStatus.CANCELLED


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
