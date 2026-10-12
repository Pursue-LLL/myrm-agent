"""Service for Agent Skill Engineering Governance and Privilege Verification.

[INPUT]
- ParseSkillContractRequest, DiffSkillContractsRequest, ValidateSkillMountingRequest

[OUTPUT]
- SkillPermissionContractDto, SkillDriftAnalysisDto, ValidateSkillMountingResponse

[POS]
- Server security service. Wraps harness skill_governance subsystem for REST API endpoints.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.core.security.skill_governance import (
    FilesystemScope,
    SkillEngineeringGovernanceGate,
    SkillPermissionContract,
    UnapprovedSkillMountError,
)

from app.schemas.skill_governance import (
    DiffSkillContractsRequest,
    ParseSkillContractRequest,
    SkillDriftAnalysisDto,
    SkillPermissionContractDto,
    ValidateSkillMountingRequest,
    ValidateSkillMountingResponse,
)


class SkillGovernanceService:
    """Singleton service providing skill contract parsing, drift diffing, and mounting authorization."""

    def __init__(self) -> None:
        self._gate = SkillEngineeringGovernanceGate

    @staticmethod
    def _convert_contract_to_domain(dto: SkillPermissionContractDto) -> SkillPermissionContract:
        """Convert DTO to domain model."""
        scope = FilesystemScope(dto.filesystem_scope)
        return SkillPermissionContract(
            skill_name=dto.skill_name,
            version=dto.version,
            declared_tools=frozenset(dto.declared_tools),
            network_egress=dto.network_egress,
            filesystem_scope=scope,
            requires_admin_review=dto.requires_admin_review,
            registered_at=dto.registered_at,
        )

    @staticmethod
    def _convert_contract_to_dto(domain: SkillPermissionContract) -> SkillPermissionContractDto:
        """Convert domain model to DTO."""
        return SkillPermissionContractDto(
            skill_name=domain.skill_name,
            version=domain.version,
            declared_tools=sorted(domain.declared_tools),
            network_egress=domain.network_egress,
            filesystem_scope=domain.filesystem_scope.value,
            requires_admin_review=domain.requires_admin_review,
            registered_at=domain.registered_at,
        )

    def parse_contract(self, request: ParseSkillContractRequest) -> SkillPermissionContractDto:
        """Parse raw SKILL.md Markdown/frontmatter into a typed permission contract."""
        contract = self._gate.parse_skill_contract(
            content=request.content,
            skill_name=request.skill_name,
            version=request.version,
        )
        return self._convert_contract_to_dto(contract)

    def diff_contracts(self, request: DiffSkillContractsRequest) -> SkillDriftAnalysisDto:
        """Analyze differences between baseline and target contracts for privilege escalations."""
        base_domain = (
            self._convert_contract_to_domain(request.base_contract)
            if request.base_contract
            else None
        )
        target_domain = self._convert_contract_to_domain(request.target_contract)

        diff = self._gate.diff_skill_contracts(base_domain, target_domain)

        return SkillDriftAnalysisDto(
            skill_name=diff.skill_name,
            base_version=diff.base_version,
            target_version=diff.target_version,
            added_tools=sorted(diff.added_tools),
            removed_tools=sorted(diff.removed_tools),
            escalated_permissions=list(diff.escalated_permissions),
            has_privilege_escalation=diff.has_privilege_escalation,
            review_required=diff.review_required,
            audit_findings=list(diff.audit_findings),
            analyzed_at=diff.analyzed_at,
        )

    def validate_mounting(
        self, request: ValidateSkillMountingRequest
    ) -> ValidateSkillMountingResponse:
        """Verify whether a skill may be mounted into agent runtime execution."""
        contract = self._convert_contract_to_domain(request.contract)
        try:
            permitted = self._gate.validate_runtime_mounting(
                contract=contract,
                is_approved=request.is_approved,
            )
            return ValidateSkillMountingResponse(
                skill_name=contract.skill_name,
                permitted=permitted,
                message="Skill contract satisfies runtime security gates and is authorized for mounting.",
            )
        except UnapprovedSkillMountError as exc:
            return ValidateSkillMountingResponse(
                skill_name=contract.skill_name,
                permitted=False,
                message=str(exc),
            )


_service_lock = threading.Lock()
_global_skill_governance_service: SkillGovernanceService | None = None


def get_skill_governance_service() -> SkillGovernanceService:
    """Retrieve or initialize global SkillGovernanceService singleton."""
    global _global_skill_governance_service
    if _global_skill_governance_service is None:
        with _service_lock:
            if _global_skill_governance_service is None:
                _global_skill_governance_service = SkillGovernanceService()
    return _global_skill_governance_service
