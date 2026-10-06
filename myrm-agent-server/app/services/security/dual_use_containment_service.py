"""
[POS] app/services/security/dual_use_containment_service.py
[INPUT] app/schemas/dual_use_containment.py, myrm_agent_harness.core.security.dual_use_containment
[OUTPUT] DualUseContainmentService, get_dual_use_containment_service

Service layer for dual-use skill containment and artifact exfiltration shield suite.

Connects the server execution layer to the harness containment suite, coordinates
HITL authorization, blocks outbound artifact leaks, and maintains flight recorder logs.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import base64
import threading
from typing import Optional

from myrm_agent_harness.core.security.dual_use_containment import (
    ArtifactSecurityClassification,
    DualUseSkillContainmentSuite,
    ExecutionGateRequest,
    SkillSensitivityLevel,
)

from app.schemas.dual_use_containment import (
    ArtifactEgressEvaluationRequest,
    ArtifactEgressEvaluationResponse,
    ArtifactSecurityClassificationEnum,
    DualUseMetricsResponse,
    EgressDestinationTrustEnum,
    ExecutionGateCheckRequest,
    ExecutionGateCheckResponse,
    FlightRecorderEntrySchema,
    MitreAttackTacticEnum,
    SkillSensitivityLevelEnum,
    SkillTtpEvaluationRequest,
    SkillTtpEvaluationResponse,
)


class DualUseContainmentService:
    """Singleton service managing dual-use skill containment and artifact egress shielding."""

    def __init__(self, allowlisted_destinations: list[str] | None = None) -> None:
        self._suite = DualUseSkillContainmentSuite(allowlisted_destinations=allowlisted_destinations)
        self._lock = threading.Lock()

        # Telemetry metrics
        self._total_skill_evaluations: int = 0
        self._dual_use_skills_detected: int = 0
        self._hitl_approvals_requested: int = 0
        self._host_execution_blocks: int = 0
        self._total_artifact_scans: int = 0
        self._exfiltration_blocks: int = 0

    def evaluate_skill_ttp(self, request: SkillTtpEvaluationRequest) -> SkillTtpEvaluationResponse:
        """Analyze a skill for MITRE ATT&CK tactics and dual-use classification."""
        spec = self._suite.evaluate_skill_ttp(
            skill_name=request.skill_name,
            description=request.description,
            command_signatures=request.command_signatures,
        )

        with self._lock:
            self._total_skill_evaluations += 1
            if spec.sensitivity_level == SkillSensitivityLevel.DUAL_USE_SENSITIVE:
                self._dual_use_skills_detected += 1

        tactics_enum_list = [MitreAttackTacticEnum(t.value) for t in spec.tactics]
        sensitivity_enum = SkillSensitivityLevelEnum(spec.sensitivity_level.value)

        return SkillTtpEvaluationResponse(
            skill_name=spec.skill_name,
            tactics=tactics_enum_list,
            sensitivity_level=sensitivity_enum,
            requires_hitl_approval=spec.requires_hitl_approval,
            quarantine_pod_enforced=spec.quarantine_pod_enforced,
            identified_signatures=spec.identified_signatures,
        )

    def check_execution_gate(self, request: ExecutionGateCheckRequest) -> ExecutionGateCheckResponse:
        """Verify quarantine pod compliance and HITL authorization before skill execution."""
        harness_req = ExecutionGateRequest(
            skill_name=request.skill_name,
            command_line=request.command_line,
            target_host_or_ip=request.target_host_or_ip,
            approval_token=request.approval_token,
            is_running_in_quarantine_pod=request.is_running_in_quarantine_pod,
        )
        res = self._suite.check_execution_gate(harness_req)

        with self._lock:
            if res.requires_hitl_modal:
                self._hitl_approvals_requested += 1
            if not res.permitted and not request.is_running_in_quarantine_pod and res.enforce_quarantine_pod:
                self._host_execution_blocks += 1

        matched_tactics = [MitreAttackTacticEnum(t.value) for t in res.matched_tactics]
        sensitivity_enum = SkillSensitivityLevelEnum(res.sensitivity_level.value)

        return ExecutionGateCheckResponse(
            permitted=res.permitted,
            requires_hitl_modal=res.requires_hitl_modal,
            sensitivity_level=sensitivity_enum,
            enforce_quarantine_pod=res.enforce_quarantine_pod,
            reason=res.reason,
            matched_tactics=matched_tactics,
            hitl_prompt_warning=res.hitl_prompt_warning,
        )

    def evaluate_artifact_egress(
        self, request: ArtifactEgressEvaluationRequest
    ) -> ArtifactEgressEvaluationResponse:
        """Inspect outbound transmission of artifacts to shield against exfiltration."""
        content_bytes = b""
        if request.content_base64:
            try:
                content_bytes = base64.b64decode(request.content_base64)
            except Exception:
                content_bytes = request.content_base64.encode("utf-8")
        else:
            content_bytes = request.artifact_name.encode("utf-8")

        explicit_cls: Optional[ArtifactSecurityClassification] = None
        if request.explicit_classification is not None:
            explicit_cls = ArtifactSecurityClassification(request.explicit_classification.value)

        audit = self._suite.evaluate_artifact_egress(
            artifact_id=request.artifact_id,
            artifact_name=request.artifact_name,
            content_bytes=content_bytes,
            target_destination=request.target_destination,
            explicit_classification=explicit_cls,
        )

        with self._lock:
            self._total_artifact_scans += 1
            if audit.is_blocked:
                self._exfiltration_blocks += 1

        cls_enum = ArtifactSecurityClassificationEnum(audit.classification.value)
        dest_trust_enum = EgressDestinationTrustEnum(audit.destination_trust.value)

        return ArtifactEgressEvaluationResponse(
            artifact_id=audit.artifact_id,
            artifact_name=audit.artifact_name,
            classification=cls_enum,
            target_destination=audit.target_destination,
            destination_trust=dest_trust_enum,
            is_blocked=audit.is_blocked,
            violation_reason=audit.violation_reason,
            sha256_hash=audit.sha256_hash,
            evaluated_at=audit.evaluated_at,
        )

    def get_flight_recorder_logs(self, limit: int = 50) -> list[FlightRecorderEntrySchema]:
        """Fetch historical tamper-evident flight recorder logs."""
        logs = self._suite.get_flight_recorder_logs(limit=limit)
        return [
            FlightRecorderEntrySchema(
                entry_id=entry.entry_id,
                event_type=entry.event_type,
                subject=entry.subject,
                decision=entry.decision,
                details=entry.details,
                timestamp=entry.timestamp,
            )
            for entry in logs
        ]

    def get_metrics(self) -> DualUseMetricsResponse:
        """Retrieve aggregated operational and security telemetry metrics."""
        with self._lock:
            return DualUseMetricsResponse(
                total_skill_evaluations=self._total_skill_evaluations,
                dual_use_skills_detected=self._dual_use_skills_detected,
                hitl_approvals_requested=self._hitl_approvals_requested,
                host_execution_blocks=self._host_execution_blocks,
                total_artifact_scans=self._total_artifact_scans,
                exfiltration_blocks=self._exfiltration_blocks,
            )


_global_service: Optional[DualUseContainmentService] = None
_global_lock = threading.Lock()


def get_dual_use_containment_service() -> DualUseContainmentService:
    """Get the singleton instance of DualUseContainmentService."""
    global _global_service
    if _global_service is None:
        with _global_lock:
            if _global_service is None:
                _global_service = DualUseContainmentService()
    return _global_service
