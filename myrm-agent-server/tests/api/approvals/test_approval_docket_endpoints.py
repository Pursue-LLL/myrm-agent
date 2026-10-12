"""Unit tests for Legal Audit Docket retrieval and JSON-LD export endpoints.

[POS]
Validates that resolving an approval automatically seals a LegalAuditDocket,
which can be queried via API and exported as cryptographically verifiable JSON-LD.
"""

from __future__ import annotations

import json

import pytest
from myrm_agent_harness.agent.security.audit_pack import (
    DocketSignature,
    LegalAuditDocket,
    LegalAuditDocketVerifier,
    TriadDelegationProof,
)

from app.services.approvals.docket_service import DocketService
from app.services.approvals.registry import ApprovalRegistry


@pytest.fixture(autouse=True)
def clear_dockets() -> None:
    """Clear cached dockets before each test."""
    DocketService.clear_dockets()


@pytest.mark.asyncio
async def test_resolve_approval_seals_docket_and_query_endpoint(client) -> None:
    """Ensure resolving an approval creates a sealed docket accessible via GET /approvals/{id}/docket."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-contract-01",
        action_type="FINANCIAL_DISBURSEMENT",
        payload={"contract_id": "CNT-8899", "amount": 50000},
        reason="Purchase of GPU server cluster",
        chat_id="chat-docket-01",
        thread_id="thread-docket-01",
    )

    # 1. Resolve approval
    resp = client.post(
        f"/api/v1/approvals/{record.id}/resolve",
        json={"decision": "approve"},
    )
    assert resp.status_code == 200

    # 2. Query docket via endpoint
    docket_resp = client.get(f"/api/v1/approvals/{record.id}/docket")
    assert docket_resp.status_code == 200
    data = docket_resp.json()

    assert data["docket_id"].startswith("docket-")
    assert data["action_type"] == "FINANCIAL_DISBURSEMENT"
    assert data["root_digest"] != ""
    assert data["signature"] is not None
    assert data["signature"]["algorithm"] == "HMAC-SHA256"
    assert "initial_requester" in data["triad_proof"]
    assert "business_approver" in data["triad_proof"]
    assert "FINANCIAL_DISBURSEMENT" in data["input_summary"]


@pytest.mark.asyncio
async def test_export_approval_docket_json_ld_and_verify(client) -> None:
    """Ensure GET /approvals/{id}/docket/export returns valid JSON-LD verifiable offline."""
    record = await ApprovalRegistry.create_approval(
        agent_id="agent-contract-02",
        action_type="SIGN_LEGAL_AGREEMENT",
        payload={"document": "NDA_Partner.pdf"},
        reason="Partner NDA signing",
        chat_id="chat-docket-02",
        thread_id="thread-docket-02",
    )

    client.post(
        f"/api/v1/approvals/{record.id}/resolve",
        json={"decision": "approve"},
    )

    export_resp = client.get(f"/api/v1/approvals/{record.id}/docket/export")
    assert export_resp.status_code == 200
    assert "application/ld+json" in export_resp.headers.get("content-type", "")
    assert f'attachment; filename="audit_docket_{record.id}.jsonld"' in export_resp.headers.get(
        "content-disposition", ""
    )

    # Parse exported JSON-LD
    exported_text = export_resp.text
    parsed_docket = json.loads(exported_text)
    assert parsed_docket["@type"] == "LegalAuditDocket"
    assert parsed_docket["action_type"] == "SIGN_LEGAL_AGREEMENT"
    assert parsed_docket["root_digest"] != ""

    # Offline Verification using LegalAuditDocketVerifier
    sig_info = parsed_docket["signature"]
    docket_obj = LegalAuditDocket(
        docket_id=parsed_docket["docket_id"],
        action_type=parsed_docket["action_type"],
        triad_proof=TriadDelegationProof.from_dict(parsed_docket["triad_proof"]),
        input_summary=parsed_docket["input_summary"],
        output_summary=parsed_docket["output_summary"],
        asset_fingerprints=(),
        execution_receipt_hashes=tuple(parsed_docket["execution_receipt_hashes"]),
        root_digest=parsed_docket["root_digest"],
        signature=DocketSignature.from_dict(sig_info) if sig_info else None,
        created_at=float(parsed_docket["created_at"]),
        metadata=dict(parsed_docket.get("metadata", {})),
    )

    signing_secret = DocketService.get_signing_secret()
    is_valid, err = LegalAuditDocketVerifier.verify_docket(docket_obj, signing_secret)
    assert is_valid is True
    assert err is None
