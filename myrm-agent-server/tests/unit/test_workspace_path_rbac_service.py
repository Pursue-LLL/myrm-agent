"""Unit tests for WorkspacePathRbacService in myrm-agent-server."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.workspace_path_rbac import (
    GranularWorkspacePathGuard,
)

from app.schemas.workspace_path_rbac import (
    CheckPathAccessRequest,
    PathRuleDto,
    WorkspacePolicyDto,
)
from app.services.security.workspace_path_rbac_service import (
    WorkspacePathRbacService,
    get_workspace_path_rbac_service,
)


@pytest.fixture
def service() -> WorkspacePathRbacService:
    guard = GranularWorkspacePathGuard()
    return WorkspacePathRbacService(guard=guard)


def test_service_register_and_get_policy(
    service: WorkspacePathRbacService,
) -> None:
    policy_dto = WorkspacePolicyDto(
        policy_id="pol_corp_01",
        user_identity="engineer@corp.com",
        project_root="/workspace/repo",
        rules=[
            PathRuleDto(pattern="data/*", mode="ro", description="Inputs"),
            PathRuleDto(pattern="output/*", mode="rw", description="Outputs"),
        ],
        allowed_deliverables_dir="output",
    )
    saved = service.register_policy(policy_dto)
    assert saved.policy_id == "pol_corp_01"

    retrieved = service.get_policy("pol_corp_01")
    assert retrieved is not None
    assert retrieved.user_identity == "engineer@corp.com"
    assert len(retrieved.rules) == 2


def test_service_check_access_and_write_denial(
    service: WorkspacePathRbacService,
) -> None:
    service.register_policy(
        WorkspacePolicyDto(
            policy_id="pol_demo",
            user_identity="analyst@corp.com",
            project_root="/workspace",
            rules=[
                PathRuleDto(pattern="raw_inputs/*", mode="ro"),
                PathRuleDto(pattern="deliverables/*", mode="rw"),
            ],
            allowed_deliverables_dir="deliverables",
        )
    )

    # 1. Allowed read
    req_read = CheckPathAccessRequest(
        policy_id="pol_demo",
        agent_id="agent_1",
        session_id="sess_1",
        user_identity="analyst@corp.com",
        relative_path="raw_inputs/stats.json",
        action="READ",
    )
    res_read = service.check_access(req_read)
    assert res_read.allowed is True
    assert res_read.effective_mode == "ro"

    # 2. Denied write with auto-reroute card
    req_write = CheckPathAccessRequest(
        policy_id="pol_demo",
        agent_id="agent_1",
        session_id="sess_1",
        user_identity="analyst@corp.com",
        relative_path="raw_inputs/stats.json",
        action="DIRECT_WRITE",
    )
    res_write = service.check_access(req_write)
    assert res_write.allowed is False
    assert res_write.violation_reason == "READ_ONLY_PATH"
    assert res_write.auto_reroute_hint is not None
    assert "deliverables/stats.json" in res_write.auto_reroute_hint
    assert res_write.denial_card is not None
    assert res_write.denial_card.blocked_path == "raw_inputs/stats.json"


def test_service_audit_ledger_query_and_stats(
    service: WorkspacePathRbacService,
) -> None:
    service.register_policy(
        WorkspacePolicyDto(
            policy_id="pol_audit",
            user_identity="auditor@corp.com",
            project_root="/workspace",
            rules=[PathRuleDto(pattern="docs/*", mode="ro")],
        )
    )

    service.check_access(
        CheckPathAccessRequest(
            policy_id="pol_audit",
            agent_id="agent_auditor",
            session_id="sess_aud",
            user_identity="auditor@corp.com",
            relative_path="docs/readme.md",
            action="READ",
        )
    )
    service.check_access(
        CheckPathAccessRequest(
            policy_id="pol_audit",
            agent_id="agent_auditor",
            session_id="sess_aud",
            user_identity="auditor@corp.com",
            relative_path="docs/readme.md",
            action="DIRECT_WRITE",
        )
    )

    entries = service.query_audit_ledger(session_id="sess_aud")
    assert len(entries) == 2

    stats = service.get_audit_stats()
    assert stats.total_events >= 2
    assert stats.granted_count >= 1
    assert stats.denied_count >= 1


def test_service_singleton() -> None:
    svc1 = get_workspace_path_rbac_service()
    svc2 = get_workspace_path_rbac_service()
    assert svc1 is svc2
