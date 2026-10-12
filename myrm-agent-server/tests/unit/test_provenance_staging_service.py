"""Unit tests for ProvenanceStagingService.

[POS]
Server unit tests verifying entity provenance tracking, two-stage change staging,
host signed authorization tokens, and business caps validation.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.provenance_gate import (
    StagedChangeNotApprovedError,
)

from app.schemas.provenance_staging import (
    ApplyStagedChangeRequest,
    CheckCapsRequest,
    CheckProvenanceRequest,
    HostApprovalTokenDto,
    IssueHostTokenRequest,
    RegisterSeenEntitiesRequest,
    RejectStagedChangeRequest,
    StageChangeRequest,
)
from app.services.security.provenance_staging_service import (
    ProvenanceStagingService,
)


def test_provenance_staging_service_provenance_flow() -> None:
    service = ProvenanceStagingService()
    session_id = "sess_unit_01"

    # 1. Register seen entities
    reg_req = RegisterSeenEntitiesRequest(
        session_id=session_id,
        entity_ids=["item_a", "item_b"],
        entity_type="catalog_item",
        source_tool="search_items",
    )
    reg_res = service.register_seen_entities(reg_req)
    assert reg_res.registered_count == 2
    assert reg_res.total_observed_count == 2

    # 2. Check provenance: observed entity allowed
    check_a = service.check_provenance(
        CheckProvenanceRequest(session_id=session_id, entity_id="item_a")
    )
    assert check_a.allowed is True

    # 3. Check provenance: unobserved entity denied
    check_unseen = service.check_provenance(
        CheckProvenanceRequest(session_id=session_id, entity_id="item_unseen_99")
    )
    assert check_unseen.allowed is False
    assert "has not been observed" in check_unseen.reason


def test_provenance_staging_service_two_stage_staging() -> None:
    service = ProvenanceStagingService()
    session_id = "sess_unit_02"

    # 1. Stage mutation draft
    stage_req = StageChangeRequest(
        session_id=session_id,
        target_entity_id="campaign_101",
        mutation_type="price_update",
        diff_payload={"old": 100, "new": 70},
    )
    draft = service.stage_change(stage_req)
    assert draft.status == "staged"
    assert draft.target_entity_id == "campaign_101"

    # 2. Issue host approval token
    issue_req = IssueHostTokenRequest(
        staged_id=draft.staged_id,
        operator_id="operator_bob",
    )
    token = service.issue_host_token(issue_req)
    assert token.staged_id == draft.staged_id
    assert len(token.signature) > 10

    # 3. Apply with forged token fails
    forged_token = HostApprovalTokenDto(
        token_id="tok_fake",
        staged_id=draft.staged_id,
        operator_id="operator_bob",
        signature="invalid_signature",
        issued_at=token.issued_at,
        valid_until=token.valid_until,
    )
    with pytest.raises(StagedChangeNotApprovedError):
        service.apply_staged_change(
            ApplyStagedChangeRequest(staged_id=draft.staged_id, token=forged_token)
        )

    # 4. Apply with authentic token succeeds
    applied = service.apply_staged_change(
        ApplyStagedChangeRequest(staged_id=draft.staged_id, token=token)
    )
    assert applied.status == "applied"
    assert applied.host_token_id == token.token_id

    # 5. Reject another draft
    draft2 = service.stage_change(
        StageChangeRequest(
            session_id=session_id,
            target_entity_id="campaign_102",
            mutation_type="delete_campaign",
        )
    )
    rejected = service.reject_staged_change(
        RejectStagedChangeRequest(staged_id=draft2.staged_id)
    )
    assert rejected.status == "rejected"


def test_provenance_staging_service_caps_check() -> None:
    service = ProvenanceStagingService()

    # 1. Compliant caps
    res_pass = service.check_caps(
        CheckCapsRequest(discount_percent=25.0, affected_rows=10, budget_delta=100.0)
    )
    assert res_pass.passed is True
    assert len(res_pass.violations) == 0

    # 2. Exceeded caps
    res_breach = service.check_caps(
        CheckCapsRequest(discount_percent=85.0, affected_rows=500, budget_delta=5000.0)
    )
    assert res_breach.passed is False
    assert len(res_breach.violations) == 3
    assert res_breach.violations[0].parameter_name == "discount_percent"
    assert res_breach.violations[0].compliant_alternative == 50.0
