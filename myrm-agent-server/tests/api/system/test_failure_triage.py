"""[INPUT]
- httpx, ASGITransport
- app.api.system.failure_triage_api::router
- app.core.infra.health.failure_triage::{FailureSymptom, BreakpointStage, NegativeOutcome}

[OUTPUT]
- Pytest test cases verifying symptom-driven triage decision trees, negative outcome classification, and in-place redispatch.

[POS]
tests/api/system/test_failure_triage.py — Agent 经典失效表象分诊决策树与自愈重发 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.system.failure_triage_api import router as failure_triage_router
from app.core.infra.health.failure_triage import (
    BreakpointStage,
    FailureSymptom,
    NegativeOutcome,
)

test_app = FastAPI()
test_app.include_router(failure_triage_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_triage_no_reply_symptom(async_client: httpx.AsyncClient) -> None:
    payload = {
        "symptom": FailureSymptom.NO_REPLY.value,
        "chat_id": "chat-triage-101",
        "trace_id": "trace-101",
    }
    resp = await async_client.post("/api/v1/system/failure-triage", json=payload)
    assert resp.status_code == 200
    report = resp.json()

    assert report["symptom"] == FailureSymptom.NO_REPLY.value
    assert report["chat_id"] == "chat-triage-101"
    assert report["root_cause_stage"] == BreakpointStage.OUTBOUND_CHANNEL.value
    assert report["can_redispatch"] is True
    assert len(report["breakdown"]) == 6


@pytest.mark.asyncio
async def test_triage_wrong_tool_denied_negative_case(async_client: httpx.AsyncClient) -> None:
    payload = {
        "symptom": FailureSymptom.WRONG_TOOL.value,
        "chat_id": "chat-triage-102",
    }
    resp = await async_client.post("/api/v1/system/failure-triage", json=payload)
    assert resp.status_code == 200
    report = resp.json()

    assert report["symptom"] == FailureSymptom.WRONG_TOOL.value
    assert report["root_cause_stage"] == BreakpointStage.TOOL_SANDBOX.value
    # 严格验证属于负例防御 (DENIED) 而非系统底层 Crash
    assert report["negative_outcome"] == NegativeOutcome.DENIED.value
    assert report["is_system_failure"] is False
    assert "安全审批防御" in report["diagnostic_message"]


@pytest.mark.asyncio
async def test_triage_custom_mock_injection(async_client: httpx.AsyncClient) -> None:
    payload = {
        "symptom": FailureSymptom.SLOW_RESPONSE.value,
        "chat_id": "chat-triage-103",
        "mock_failure_stage": BreakpointStage.SESSION_LOCK.value,
        "mock_negative_outcome": NegativeOutcome.TIMEOUT.value,
    }
    resp = await async_client.post("/api/v1/system/failure-triage", json=payload)
    assert resp.status_code == 200
    report = resp.json()

    assert report["root_cause_stage"] == BreakpointStage.SESSION_LOCK.value
    assert report["negative_outcome"] == NegativeOutcome.TIMEOUT.value
    assert report["is_system_failure"] is True


@pytest.mark.asyncio
async def test_in_place_redispatch_endpoint(async_client: httpx.AsyncClient) -> None:
    payload = {
        "chat_id": "chat-triage-104",
        "stage": BreakpointStage.OUTBOUND_CHANNEL.value,
        "reason": "user_clicked_redispatch",
    }
    resp = await async_client.post("/api/v1/system/failure-triage/redispatch", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["success"] is True
    assert data["chat_id"] == "chat-triage-104"
    assert data["stage"] == BreakpointStage.OUTBOUND_CHANNEL.value
    assert "已成功在断点" in data["message"]
