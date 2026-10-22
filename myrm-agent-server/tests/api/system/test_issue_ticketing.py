"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.issue_ticketing_api::router
- myrm_agent_harness.observability.diagnostics_bundle::DiagnosticBundlePackager

[OUTPUT]:
- Pytest test cases verifying ticket submission, bundle HMAC verification, ticket retrieval, and in-place self-heal reboot APIs.

[POS]:
tests/api/system/test_issue_ticketing.py — 端内诊断打包与工单自愈系统 API 单元测试。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.issue_ticketing_api import router as issue_ticketing_router
from myrm_agent_harness.observability.diagnostics_bundle import (
    ClientContext,
    DiagnosticBundlePackager,
    DiagnosticLogEvent,
    SandboxVitals,
)

test_app = FastAPI()
test_app.include_router(issue_ticketing_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_submit_valid_diagnostic_bundle(async_client: httpx.AsyncClient) -> None:
    packager = DiagnosticBundlePackager()

    vitals = SandboxVitals(
        cpu_pct=96.2,
        mem_pct=94.5,
        disk_free_bytes=50000000,
        network_state="degraded",
        uptime_secs=1200.0,
        is_volume_healthy=True,
    )
    logs = [
        DiagnosticLogEvent(
            timestamp="2026-10-12T10:00:00Z",
            level="CRITICAL",
            subsystem="sandbox_kernel",
            message="Out of memory: Kill process 1249 (python3)",
            metadata={"source": "kernel_oom_watcher"},
        )
    ]
    client_ctx = ClientContext(
        client_version="1.5.0",
        platform="darwin",
        browser_or_os="macOS 15.1 / Chrome 130",
        active_route="/tasks/run-99",
        session_id="session-alpha-42",
    )

    bundle = packager.package(
        session_id="session-alpha-42",
        sandbox_id="sbx-vol-01",
        vitals=vitals,
        raw_logs=logs,
        client_context=client_ctx,
    )

    payload = bundle.to_dict()
    payload["user_description"] = "Sandbox frozen suddenly during compilation"

    resp = await async_client.post("/api/v1/system/tickets/submit", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["ticket_id"].startswith("TICKET-")
    assert data["bundle_id"] == bundle.bundle_id
    assert data["status"] == "DISPATCHED"
    assert data["sla_target_minutes"] == 15
    assert "内存超警戒水位" in data["auto_diagnosis"]
    assert len(data["suggested_actions"]) > 0

    # Verify query ticket
    ticket_id = data["ticket_id"]
    query_resp = await async_client.get(f"/api/v1/system/tickets/{ticket_id}")
    assert query_resp.status_code == 200
    query_data = query_resp.json()
    assert query_data["ticket_id"] == ticket_id
    assert len(query_data["status_history"]) >= 2


@pytest.mark.asyncio
async def test_submit_tampered_bundle_fails(async_client: httpx.AsyncClient) -> None:
    packager = DiagnosticBundlePackager()
    vitals = SandboxVitals(
        cpu_pct=10.0,
        mem_pct=20.0,
        disk_free_bytes=1000000000,
        network_state="healthy",
        uptime_secs=300.0,
    )
    logs = [
        DiagnosticLogEvent(
            timestamp="2026-10-12T10:00:00Z",
            level="INFO",
            subsystem="agent",
            message="Heartbeat OK",
        )
    ]
    client_ctx = ClientContext(
        client_version="1.0.0",
        platform="web",
        browser_or_os="Firefox",
        active_route="/",
        session_id="sess-tamper",
    )

    bundle = packager.package(
        session_id="sess-tamper",
        sandbox_id="sbx-01",
        vitals=vitals,
        raw_logs=logs,
        client_context=client_ctx,
    )

    payload = bundle.to_dict()
    # Tamper checksum
    payload["checksum"] = "badc0ffee0000000000000000000000000000000000000000000000000000000"

    resp = await async_client.post("/api/v1/system/tickets/submit", json=payload)
    assert resp.status_code == 400
    assert "完整性校验失败" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_nonexistent_ticket_returns_404(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/system/tickets/TICKET-99999999-NOTFOUND")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_self_heal_reboot_sandbox(async_client: httpx.AsyncClient) -> None:
    sandbox_id = "sbx-prod-user-99"
    resp = await async_client.post(
        f"/api/v1/system/sandbox/{sandbox_id}/self-heal-reboot",
        json={"reason": "User clicked in-place reboot"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sandbox_id"] == sandbox_id
    assert data["status"] == "REBOOT_SUCCESS"
    assert data["volume_intact"] is True
    assert data["recovered_in_seconds"] > 0
    assert "持久化 Volume" in data["message"]
