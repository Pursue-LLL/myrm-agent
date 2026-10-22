"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.evidence_cross_verification_api::router

[OUTPUT]:
- Pytest verification for multi-source evidence cross-verification and 4-tier confidence scoring API endpoints.

[POS]:
tests/api/system/test_evidence_cross_verification_api.py — 多源证据交叉验证与四分制置信度 API 单元测试。
"""

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.evidence_cross_verification_api import router as evidence_router

test_app = FastAPI()
test_app.include_router(evidence_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_evidence_cross_verification_api_flow(async_client: httpx.AsyncClient) -> None:
    # 1. Reset engine
    reset_resp = await async_client.post("/api/v1/system/evidence-verification/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"ok": True}

    # 2. Check initial empty history
    history_resp = await async_client.get("/api/v1/system/evidence-verification/recent-diagnoses")
    assert history_resp.status_code == 200
    assert history_resp.json() == []

    # 3. Record multi-source evidence items
    r_kb = await async_client.post(
        "/api/v1/system/evidence-verification/record-evidence",
        json={
            "source_type": "KNOWLEDGE_BASE",
            "title": "Payment SLA Runbook",
            "detail": "Gateway maximum execution deadline is 3000ms",
            "is_verified": True,
        },
    )
    assert r_kb.status_code == 200

    r_sym = await async_client.post(
        "/api/v1/system/evidence-verification/record-evidence",
        json={
            "source_type": "CODE_SYMBOL",
            "title": "PaymentRouter Definition",
            "detail": "Function route_checkout defined",
            "is_verified": True,
            "file_path": "app/services/checkout.py",
            "line_number": 42,
        },
    )
    assert r_sym.status_code == 200

    r_log = await async_client.post(
        "/api/v1/system/evidence-verification/record-evidence",
        json={
            "source_type": "SOURCE_LOGIC",
            "title": "Serial Retry Loop",
            "detail": "Synchronous loop awaiting sequential downstream calls",
            "is_verified": True,
            "file_path": "app/services/checkout.py",
            "line_number": 58,
        },
    )
    assert r_log.status_code == 200

    r_rt = await async_client.post(
        "/api/v1/system/evidence-verification/record-evidence",
        json={
            "source_type": "RUNTIME_TELEMETRY",
            "title": "Distributed Trace Span",
            "detail": "Trace observed cumulative timeout of 5800ms before aborting",
            "is_verified": True,
            "trace_id": "tr_pay_9981",
        },
    )
    assert r_rt.status_code == 200

    # 4. Trigger root-cause diagnosis with full 4-tier proof and resolved error code
    diag_resp = await async_client.post(
        "/api/v1/system/evidence-verification/diagnose",
        json={
            "error_code": "ERR_GATEWAY_TIMEOUT",
            "event_date": "2026-10-13",
            "caller_trace_id": "tr_pay_9981",
            "raw_symptom": "Checkout call stalled and aborted with 504",
            "kb_doc_hint": "Payment Gateway Deadline Exceeded",
            "code_def_hint": "ERR_PAYMENT_GATEWAY_TIMEOUT",
            "call_budget": 15,
        },
    )
    assert diag_resp.status_code == 200
    diag_data = diag_resp.json()

    assert diag_data["error_code"] == "ERR_GATEWAY_TIMEOUT"
    assert "ERR_PAYMENT_GATEWAY_TIMEOUT" in diag_data["resolved_code_meaning"]
    assert diag_data["target_file_path"] == "app/services/checkout.py"
    assert diag_data["target_line_number"] == 58
    assert diag_data["root_cause_category"] == "CUMULATIVE_TIMEOUT"
    assert diag_data["confidence_score"] == 4
    assert diag_data["confidence_level"] == "HIGH"
    assert diag_data["bilateral_verified"] is True
    assert len(diag_data["evidences"]) == 4

    # 5. Trigger second diagnosis with completely unknown error code (demonstrating hard guard capping at MEDIUM)
    unknown_resp = await async_client.post(
        "/api/v1/system/evidence-verification/diagnose",
        json={
            "error_code": "OBSCURE_ERR_9999",
            "event_date": "2026-10-13",
            "caller_trace_id": "tr_pay_9981",
            "raw_symptom": "Unrecognized error code",
            "kb_doc_hint": "",
            "code_def_hint": "",
            "call_budget": 15,
        },
    )
    assert unknown_resp.status_code == 200
    unknown_data = unknown_resp.json()
    assert unknown_data["resolved_code_meaning"] == "ErrUnknown_OBSCURE_ERR_9999"
    # Even with all 4 evidences, unresolved error code caps confidence strictly at MEDIUM (score 2)
    assert unknown_data["confidence_score"] == 2
    assert unknown_data["confidence_level"] == "MEDIUM"

    # 6. Verify recent diagnoses list
    recent_resp = await async_client.get(
        "/api/v1/system/evidence-verification/recent-diagnoses",
        params={"limit": 10},
    )
    assert recent_resp.status_code == 200
    recent_items = recent_resp.json()
    assert len(recent_items) == 2
