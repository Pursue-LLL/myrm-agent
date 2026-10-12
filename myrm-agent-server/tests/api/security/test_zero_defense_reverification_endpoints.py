"""API endpoint tests for Zero-Defense Error Acknowledgment and Grounded Re-Verification."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.zero_defense_reverification_router import (
    router as zero_defense_reverification_router,
)
from app.services.security.zero_defense_reverification_service import (
    ZeroDefenseReVerificationService,
    get_zero_defense_reverification_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ZeroDefenseReVerificationService()
    test_service.reset_all()
    app = FastAPI()
    app.include_router(zero_defense_reverification_router)
    app.dependency_overrides[get_zero_defense_reverification_service] = lambda: test_service
    return TestClient(app)


def test_detect_dispute_endpoint(client: TestClient) -> None:
    # 1. Dispute detection
    resp1 = client.post(
        "/security/zero-defense-reverification/detect-dispute",
        json={"user_utterance": "你算错了，财务报表里的净利率不是 15%！"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["is_dispute"] is True
    assert data1["intent_type"] == "CALCULATION_ERROR"
    assert "重新核查" in data1["mandatory_protocol_phrase"]

    # 2. Normal text
    resp2 = client.post(
        "/security/zero-defense-reverification/detect-dispute",
        json={"user_utterance": "帮我润色一下这份报告的引言部分。"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_dispute"] is False
    assert data2["intent_type"] is None


def test_cross_check_endpoints(client: TestClient) -> None:
    # Fail-closed check with empty citations
    resp_empty = client.post(
        "/security/zero-defense-reverification/cross-check",
        json={
            "dispute_anchor": "Tax exemption rate",
            "prior_conclusion": "Tax rate is 0%",
            "citations": [],
        },
    )
    assert resp_empty.status_code == 200
    data_empty = resp_empty.json()
    assert data_empty["verdict"] == "AMBIGUOUS_ESCALATE"
    assert data_empty["requires_expert_escalation"] is True

    # Grounded evidence check
    resp_grounded = client.post(
        "/security/zero-defense-reverification/cross-check",
        json={
            "dispute_anchor": "IP ownership clause",
            "prior_conclusion": "Contractor retains all IP ownership",
            "citations": [
                {
                    "source_path": "legal/ip_assignment.pdf",
                    "line_or_location": "Clause 8.1",
                    "quote_snippet": "All work product shall be works made for hire owned exclusively by Company.",
                }
            ],
            "high_risk_domain": "legal",
        },
    )
    assert resp_grounded.status_code == 200
    data_grounded = resp_grounded.json()
    assert data_grounded["verdict"] == "CORRECTED"
    assert "ip_assignment.pdf" in data_grounded["correction_explanation"]


def test_escalation_ticket_endpoints_lifecycle(client: TestClient) -> None:
    # Create ticket
    create_resp = client.post(
        "/security/zero-defense-reverification/tickets",
        json={
            "session_id": "sess-dispute-001",
            "risk_domain": "finance",
            "dispute_summary": "Disputed valuation multiple applied in DCF analysis",
            "prior_conclusion": "Valuation multiple applied was 18.5x",
            "citations": [
                {
                    "source_path": "financials/dcf_model.xlsx",
                    "line_or_location": "Sheet1!B24",
                    "quote_snippet": "Baseline multiple: 12.0x",
                }
            ],
        },
    )
    assert create_resp.status_code == 200
    ticket = create_resp.json()
    ticket_id = ticket["ticket_id"]
    assert ticket["status"] == "OPEN"

    # Query ticket
    get_resp = client.get(f"/security/zero-defense-reverification/tickets/{ticket_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["ticket_id"] == ticket_id

    # Resolve ticket
    resolve_resp = client.post(
        f"/security/zero-defense-reverification/tickets/{ticket_id}/resolve",
        json={"resolution_notes": "Financial auditor approved revision to 12.0x multiple."},
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["status"] == "RESOLVED"
    assert "12.0x" in resolve_resp.json()["resolution_notes"]

    # 404 tests
    missing_get = client.get("/security/zero-defense-reverification/tickets/non-existent-ticket")
    assert missing_get.status_code == 404

    missing_resolve = client.post(
        "/security/zero-defense-reverification/tickets/non-existent-ticket/resolve",
        json={"resolution_notes": "Note"},
    )
    assert missing_resolve.status_code == 404
