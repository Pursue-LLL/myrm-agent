"""
[POS] tests/unit/test_readonly_research_sandbox_service.py
[INPUT] app.services.security.readonly_research_sandbox_service, app.schemas.readonly_research_sandbox
[OUTPUT] Unit tests for ReadOnlyResearchSandboxService

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.readonly_research_sandbox import (
    GrantLeaseRequest,
    LeaseStatusEnum,
    ResearchModeEnum,
    TakeSnapshotRequest,
    ToolEvaluationRequest,
    VerifyPurityRequest,
    WriteEphemeralFileRequest,
)
from app.services.security.readonly_research_sandbox_service import (
    ReadOnlyResearchSandboxService,
)


def test_service_grant_and_evaluate_lease() -> None:
    """Test granting read-only lease, evaluating tool access, and revoking lease."""
    service = ReadOnlyResearchSandboxService()
    session_id = "sess-svc-ro-01"

    # 1. Grant lease
    lease = service.grant_lease(
        GrantLeaseRequest(
            session_id=session_id,
            research_mode=ResearchModeEnum.AUTONOMOUS_RESEARCH,
            ttl_seconds=3600.0,
        )
    )
    assert lease.status == LeaseStatusEnum.ACTIVE
    assert lease.research_mode == ResearchModeEnum.AUTONOMOUS_RESEARCH

    # 2. Safe read tool allowed
    eval_r = service.evaluate_tool(
        ToolEvaluationRequest(session_id=session_id, tool_name="read_file")
    )
    assert eval_r.is_allowed is True
    assert eval_r.is_read_only_enforced is True

    # 3. Destructive write tool blocked
    eval_w = service.evaluate_tool(
        ToolEvaluationRequest(session_id=session_id, tool_name="write_file")
    )
    assert eval_w.is_allowed is False
    assert "physically stripped" in eval_w.explanation

    # 4. Revoke lease
    rev_resp = service.revoke_lease(session_id)
    assert rev_resp.status == LeaseStatusEnum.REVOKED

    # Post-revocation tool permitted
    eval_post = service.evaluate_tool(
        ToolEvaluationRequest(session_id=session_id, tool_name="write_file")
    )
    assert eval_post.is_allowed is True
    assert eval_post.is_read_only_enforced is False


def test_service_snapshot_and_purity_verification() -> None:
    """Test workspace baseline snapshotting and purity verification."""
    service = ReadOnlyResearchSandboxService()
    session_id = "sess-snap-svc"
    files = {"analysis.py": "import pandas as pd", "data.json": "{}"}

    # 1. Take snapshot
    snap = service.take_snapshot(
        TakeSnapshotRequest(session_id=session_id, baseline_files=files)
    )
    assert snap.tracked_files_count == 2
    assert len(snap.root_digest) == 64

    # 2. Purity matches
    pur_resp = service.verify_purity(
        VerifyPurityRequest(session_id=session_id, current_files=files)
    )
    assert pur_resp.is_pure is True

    # 3. Purity fails if modified
    polluted = dict(files)
    polluted["polluted.tmp"] = "side effect"
    pur_fail = service.verify_purity(
        VerifyPurityRequest(session_id=session_id, current_files=polluted)
    )
    assert pur_fail.is_pure is False
    assert "Pollution detected" in pur_fail.explanation


def test_service_ephemeral_cow_and_purge() -> None:
    """Test staging temporary files into in-memory CoW layer and purging them."""
    service = ReadOnlyResearchSandboxService()
    session_id = "sess-cow-svc"

    # Write ephemeral file
    f_res = service.write_ephemeral_file(
        WriteEphemeralFileRequest(
            session_id=session_id,
            virtual_path="charts/trend.svg",
            content="<svg></svg>",
        )
    )
    assert f_res.virtual_path == "charts/trend.svg"
    assert len(f_res.sha256_hash) == 64

    # List files
    staged = service.list_ephemeral_files(session_id)
    assert len(staged) == 1
    assert staged[0].virtual_path == "charts/trend.svg"

    # Purge
    purge_res = service.purge_overlay(session_id)
    assert purge_res.purged_files_count == 1
    assert len(service.list_ephemeral_files(session_id)) == 0


def test_service_shield_badge_and_metrics() -> None:
    """Test UI security badge construction and cumulative metrics retrieval."""
    service = ReadOnlyResearchSandboxService()
    session_id = "sess-badge-svc"

    # Grant lease
    service.grant_lease(
        GrantLeaseRequest(
            session_id=session_id,
            research_mode=ResearchModeEnum.BACKGROUND_STUDY,
        )
    )

    # Get badge
    badge = service.get_shield_badge(session_id)
    assert badge.is_read_only_active is True
    assert badge.research_mode == ResearchModeEnum.BACKGROUND_STUDY
    assert "Read-Only" in badge.badge_label

    # Metrics
    metrics = service.get_metrics()
    assert metrics.total_leases_granted >= 1
    assert metrics.active_leases_count >= 1
