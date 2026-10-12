"""Unit tests for SkillGovernanceService in server layer.

[POS]
Server unit tests verifying skill contract parsing, drift analysis with
privilege escalation detection, and runtime mounting validation.
"""

from __future__ import annotations

from app.schemas.skill_governance import (
    DiffSkillContractsRequest,
    ParseSkillContractRequest,
    SkillPermissionContractDto,
    ValidateSkillMountingRequest,
)
from app.services.security.skill_governance_service import SkillGovernanceService


def test_skill_governance_service_parse_contract() -> None:
    service = SkillGovernanceService()

    content = (
        "---\n"
        "tools:\n"
        "  - web_search\n"
        "  - bash_code_execute\n"
        "network_egress: true\n"
        "filesystem_scope: full_access\n"
        "---\n"
        "# CI Agent Skill\n"
        "Automated deployment runner.\n"
    )

    contract_dto = service.parse_contract(
        ParseSkillContractRequest(
            content=content,
            skill_name="ci_deployer",
            version="1.0.0",
        )
    )

    assert contract_dto.skill_name == "ci_deployer"
    assert "bash_code_execute" in contract_dto.declared_tools
    assert contract_dto.network_egress is True
    assert contract_dto.filesystem_scope == "full_access"
    assert contract_dto.requires_admin_review is True


def test_skill_governance_service_diff_escalation() -> None:
    service = SkillGovernanceService()

    base_dto = SkillPermissionContractDto(
        skill_name="code_reviewer",
        version="1.0.0",
        declared_tools=["web_search", "file_read"],
        network_egress=False,
        filesystem_scope="task_workspace",
        requires_admin_review=False,
    )

    target_dto = SkillPermissionContractDto(
        skill_name="code_reviewer",
        version="1.1.0",
        declared_tools=["web_search", "file_read", "bash"],
        network_egress=True,
        filesystem_scope="full_access",
        requires_admin_review=True,
    )

    diff = service.diff_contracts(
        DiffSkillContractsRequest(
            base_contract=base_dto,
            target_contract=target_dto,
        )
    )

    assert diff.skill_name == "code_reviewer"
    assert diff.has_privilege_escalation is True
    assert diff.review_required is True
    assert "bash" in diff.added_tools
    assert any("added_high_risk_tool:bash" in p for p in diff.escalated_permissions)
    assert any("escalated_network_egress" in p for p in diff.escalated_permissions)


def test_skill_governance_service_validate_mounting() -> None:
    service = SkillGovernanceService()

    danger_dto = SkillPermissionContractDto(
        skill_name="database_admin",
        version="1.0.0",
        declared_tools=["db_mutate"],
        network_egress=False,
        filesystem_scope="task_workspace",
        requires_admin_review=True,
    )

    # 1. Unapproved -> blocked
    unapproved_res = service.validate_mounting(
        ValidateSkillMountingRequest(contract=danger_dto, is_approved=False)
    )
    assert unapproved_res.permitted is False
    assert "lacks mandatory administrator approval" in unapproved_res.message

    # 2. Approved -> permitted
    approved_res = service.validate_mounting(
        ValidateSkillMountingRequest(contract=danger_dto, is_approved=True)
    )
    assert approved_res.permitted is True
