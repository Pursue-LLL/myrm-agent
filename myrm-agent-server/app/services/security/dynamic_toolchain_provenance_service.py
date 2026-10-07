"""
[POS] app/services/security/dynamic_toolchain_provenance_service.py
[INPUT] app.schemas.dynamic_toolchain_provenance, myrm_agent_harness.core.security.dynamic_toolchain_provenance
[OUTPUT] DynamicToolchainProvenanceService, get_dynamic_toolchain_provenance_service

Service layer for Dynamic Toolchain Supply Chain Provenance & Pre-Install Sandbox Hardening.
Orchestrates cryptographic provenance verification, static AST safety screening,
and JIT least-privilege sandbox confinement profile lifecycle.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.dynamic_toolchain_provenance import (
    ASTScanFinding,
    DynamicToolchainProvenanceSuite,
    SandboxConfinementPolicy,
    SkillProvenanceManifest,
    ToolchainVerificationDecision,
)

from app.schemas.dynamic_toolchain_provenance import (
    ASTScanFindingResponse,
    CheckPermissionRequest,
    CheckPermissionResponse,
    DynamicToolchainMetricsResponse,
    EvaluateAndInstallSkillRequest,
    ManagePublisherRequest,
    SandboxConfinementPolicyResponse,
    ScanASTOnlyRequest,
    ScanASTOnlyResponse,
    SkillProvenanceManifestSchema,
    ToolchainVerificationDecisionResponse,
    VerifyProvenanceOnlyRequest,
    VerifyProvenanceOnlyResponse,
)

logger = logging.getLogger(__name__)


class DynamicToolchainProvenanceService:
    """Service mediating dynamic skill supply-chain screening and sandbox confinement."""

    def __init__(self, suite: DynamicToolchainProvenanceSuite | None = None) -> None:
        self._suite = suite or DynamicToolchainProvenanceSuite()

    def evaluate_and_install_skill(
        self,
        request: EvaluateAndInstallSkillRequest,
    ) -> ToolchainVerificationDecisionResponse:
        """Run full gate: provenance verification, AST scan, and JIT confinement."""
        manifest = self._manifest_from_schema(request.manifest)
        decision = self._suite.evaluate_and_install_skill(
            source_code=request.source_code,
            manifest=manifest,
        )
        return self._map_decision(decision)

    def verify_provenance_only(
        self,
        request: VerifyProvenanceOnlyRequest,
    ) -> VerifyProvenanceOnlyResponse:
        """Verify publisher signature and SHA-256 digest only."""
        manifest = self._manifest_from_schema(request.manifest)
        status, explanation = self._suite.verify_provenance_only(
            source_code=request.source_code,
            manifest=manifest,
        )
        return VerifyProvenanceOnlyResponse(
            provenance_status=status.value,
            explanation=explanation,
        )

    def scan_ast_only(self, request: ScanASTOnlyRequest) -> ScanASTOnlyResponse:
        """Run standalone static AST safety scan on code snippet."""
        findings = self._suite.scan_ast_only(
            source_code=request.source_code,
            skill_id=request.skill_id,
        )
        return ScanASTOnlyResponse(
            skill_id=request.skill_id,
            findings=self._map_findings(findings),
            is_clean=len(findings) == 0,
        )

    def register_trusted_publisher(self, request: ManagePublisherRequest) -> bool:
        """Add a publisher to trusted identity set."""
        self._suite.register_trusted_publisher(request.publisher_id)
        return True

    def revoke_trusted_publisher(self, request: ManagePublisherRequest) -> bool:
        """Remove a publisher from trusted identity set."""
        self._suite.revoke_trusted_publisher(request.publisher_id)
        return True

    def check_permission(self, request: CheckPermissionRequest) -> CheckPermissionResponse:
        """Check whether target operation is allowed under confinement policy."""
        domain_policy = self._policy_from_schema(request.policy)
        target_type = request.target_type.strip().lower()
        val = request.target_value.strip()

        if target_type == "network":
            permitted = self._suite.is_network_call_permitted(domain_policy, val)
        elif target_type == "path":
            permitted = self._suite.is_path_access_permitted(domain_policy, val)
        elif target_type == "env":
            permitted = self._suite.is_env_access_permitted(domain_policy, val)
        else:
            permitted = False

        return CheckPermissionResponse(
            permitted=permitted,
            target_type=target_type,
            target_value=val,
        )

    def get_metrics(self) -> DynamicToolchainMetricsResponse:
        """Retrieve metrics snapshot."""
        m = self._suite.metrics
        return DynamicToolchainMetricsResponse(
            provenance_checks_total=m.provenance_checks_total,
            provenance_verified_total=m.provenance_verified_total,
            provenance_rejected_total=m.provenance_rejected_total,
            ast_scans_total=m.ast_scans_total,
            ast_violations_detected_total=m.ast_violations_detected_total,
            confinements_issued_total=m.confinements_issued_total,
            installations_approved_total=m.installations_approved_total,
            installations_blocked_total=m.installations_blocked_total,
        )

    @staticmethod
    def _manifest_from_schema(schema: SkillProvenanceManifestSchema) -> SkillProvenanceManifest:
        return SkillProvenanceManifest(
            skill_id=schema.skill_id,
            version=schema.version,
            publisher_id=schema.publisher_id,
            source_sha256=schema.source_sha256,
            signature=schema.signature,
            declared_domains=list(schema.declared_domains),
            declared_paths=list(schema.declared_paths),
            declared_env_keys=list(schema.declared_env_keys),
        )

    @staticmethod
    def _policy_from_schema(schema: SandboxConfinementPolicyResponse) -> SandboxConfinementPolicy:
        return SandboxConfinementPolicy(
            policy_id=schema.policy_id,
            skill_id=schema.skill_id,
            allowed_domains=list(schema.allowed_domains),
            allowed_paths=list(schema.allowed_paths),
            allowed_env_keys=list(schema.allowed_env_keys),
            is_confined=schema.is_confined,
            created_at=schema.created_at,
        )

    @classmethod
    def _map_decision(
        cls,
        decision: ToolchainVerificationDecision,
    ) -> ToolchainVerificationDecisionResponse:
        policy_resp = cls._map_policy(decision.confinement_policy) if decision.confinement_policy else None
        return ToolchainVerificationDecisionResponse(
            skill_id=decision.skill_id,
            provenance_status=decision.provenance_status.value,
            is_provenance_valid=decision.is_provenance_valid,
            ast_findings=cls._map_findings(decision.ast_findings),
            is_ast_clean=decision.is_ast_clean,
            is_installation_approved=decision.is_installation_approved,
            confinement_policy=policy_resp,
            explanation=decision.explanation,
            timestamp=decision.timestamp,
        )

    @staticmethod
    def _map_policy(policy: SandboxConfinementPolicy) -> SandboxConfinementPolicyResponse:
        return SandboxConfinementPolicyResponse(
            policy_id=policy.policy_id,
            skill_id=policy.skill_id,
            allowed_domains=list(policy.allowed_domains),
            allowed_paths=list(policy.allowed_paths),
            allowed_env_keys=list(policy.allowed_env_keys),
            is_confined=policy.is_confined,
            created_at=policy.created_at,
        )

    @staticmethod
    def _map_findings(findings: list[ASTScanFinding]) -> list[ASTScanFindingResponse]:
        return [
            ASTScanFindingResponse(
                violation_type=f.violation_type.value,
                symbol_name=f.symbol_name,
                line_number=f.line_number,
                detail=f.detail,
            )
            for f in findings
        ]


_default_service: DynamicToolchainProvenanceService | None = None


def get_dynamic_toolchain_provenance_service() -> DynamicToolchainProvenanceService:
    """Dependency provider returning singleton instance of DynamicToolchainProvenanceService."""
    global _default_service
    if _default_service is None:
        _default_service = DynamicToolchainProvenanceService()
    return _default_service
