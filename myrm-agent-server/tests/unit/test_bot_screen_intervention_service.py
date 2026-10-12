"""
Unit tests for Bot Screen Auditable Operational Control & Intervention Evidence Service.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.schemas.bot_screen_intervention import (
    ClassifyElementRiskRequest,
    EvaluateScreenActionRequest,
    RecordInterventionEventRequest,
    SealEvidenceBundleRequest,
    StartInterventionRequest,
    VerifyScreenAssertionRequest,
)
from app.services.security.bot_screen_intervention_service import (
    BotScreenInterventionService,
)


def test_service_classify_element_risk() -> None:
    service = BotScreenInterventionService()

    # Financial interaction
    req_fin = ClassifyElementRiskRequest(
        selector="#submit-vendor-payout",
        label="Approve Payout",
        action_type="click",
    )
    resp_fin = service.classify_element_risk(req_fin)
    assert resp_fin.risk_tier == "HIGH_RISK_FINANCIAL"

    # Critical admin
    req_crit = ClassifyElementRiskRequest(
        selector="#truncate-db-records",
        label="Truncate Table",
        action_type="click",
    )
    resp_crit = service.classify_element_risk(req_crit)
    assert resp_crit.risk_tier == "CRITICAL_ADMIN"

    # Standard write
    req_write = ClassifyElementRiskRequest(
        selector="#notes",
        label="Delivery Notes",
        action_type="type",
    )
    resp_write = service.classify_element_risk(req_write)
    assert resp_write.risk_tier == "STANDARD_WRITE"


def test_service_evaluate_action() -> None:
    service = BotScreenInterventionService()

    # 1. Financial action requires approval checkpoint
    req_fin = EvaluateScreenActionRequest(
        action_id="act-pay-1",
        target_selector="#btn-pay-now",
        action_type="click",
        label="Pay Invoice $12,000",
        risk_tier="HIGH_RISK_FINANCIAL",
    )
    resp_fin = service.evaluate_action(req_fin)
    assert resp_fin.decision == "PENDING_HUMAN_APPROVAL"
    assert "checkpoint approval" in resp_fin.reason

    # 2. Critical action mandates manual takeover
    req_crit = EvaluateScreenActionRequest(
        action_id="act-crit-1",
        target_selector="#btn-delete-tenant",
        action_type="click",
        label="Delete Tenant Profile",
        risk_tier="CRITICAL_ADMIN",
    )
    resp_crit = service.evaluate_action(req_crit)
    assert resp_crit.decision == "MANUAL_TAKEOVER_REQUIRED"
    assert "manual human takeover" in resp_crit.reason

    # 3. Standard write auto approved
    req_norm = EvaluateScreenActionRequest(
        action_id="act-norm-1",
        target_selector="#input-memo",
        action_type="type",
        label="Input Memo",
        risk_tier="STANDARD_WRITE",
    )
    resp_norm = service.evaluate_action(req_norm)
    assert resp_norm.decision == "APPROVED_AUTOMATIC"


def test_service_intervention_lifecycle() -> None:
    service = BotScreenInterventionService()

    # 1. Start intervention
    start_req = StartInterventionRequest(
        session_id="session-erp-42",
        operator_id="operator_bob",
        before_snapshot_hash="hash_before_999",
    )
    start_resp = service.start_intervention(start_req)
    intervene_id = start_resp.intervention_id
    assert intervene_id.startswith("intervene-")

    # 2. Record keystroke/mouse actions
    rec_req1 = RecordInterventionEventRequest(
        intervention_id=intervene_id,
        event_type="mouse_click",
        target_selector="#table-row-5",
        raw_data="selected row",
    )
    evt1 = service.record_event(rec_req1)
    assert evt1.target_selector == "#table-row-5"
    assert evt1.data_sanitized == "selected row"

    # Redaction test for password
    rec_req2 = RecordInterventionEventRequest(
        intervention_id=intervene_id,
        event_type="keyboard_input",
        target_selector="#user-password",
        raw_data="unredacted_password_value",
    )
    evt2 = service.record_event(rec_req2)
    assert evt2.data_sanitized == "[REDACTED_SENSITIVE_CREDENTIAL]"

    # 3. Seal evidence bundle
    seal_req = SealEvidenceBundleRequest(
        intervention_id=intervene_id,
        after_snapshot_hash="hash_after_888",
    )
    bundle = service.seal_evidence_bundle(seal_req)
    assert bundle.intervention_id == intervene_id
    assert bundle.event_count == 2
    assert bundle.is_tamper_evident
    assert len(bundle.bundle_sha256) == 64

    # 4. Query sealed bundle
    retrieved = service.get_evidence_bundle(intervene_id)
    assert retrieved.intervention_id == intervene_id
    assert retrieved.bundle_sha256 == bundle.bundle_sha256

    # 5. Missing bundle throws 404
    with pytest.raises(HTTPException) as exc:
        service.get_evidence_bundle("non-existent-intervene-id")
    assert exc.value.status_code == 404


def test_service_verify_screen_assertion_and_metrics() -> None:
    service = BotScreenInterventionService()

    # Pass assertion
    pass_req = VerifyScreenAssertionRequest(
        probe_id="p-success",
        expected_selector="#toast-success",
        expected_text_contains="Batch saved",
        actual_text="Success: Batch saved to ERP system.",
        visual_hash_match=True,
    )
    p_pass = service.verify_screen_assertion(pass_req)
    assert p_pass.passed

    # Fail assertion
    fail_req = VerifyScreenAssertionRequest(
        probe_id="p-fail",
        expected_selector="#toast-success",
        expected_text_contains="Batch saved",
        actual_text="Error: Connection refused.",
        visual_hash_match=True,
    )
    p_fail = service.verify_screen_assertion(fail_req)
    assert not p_fail.passed

    metrics = service.get_metrics()
    assert metrics.assertion_failures == 1
