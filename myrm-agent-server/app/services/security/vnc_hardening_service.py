"""
[POS] app/services/security/vnc_hardening_service.py
[INPUT] app.schemas.vnc_hardening, myrm_agent_harness.core.security.vnc_hardening
[OUTPUT] VncHardeningService, get_vnc_hardening_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.vnc_hardening import (
    VncBindMode,
    VncHardenedLaunchSpec,
    VncHardeningAuditReport,
    VncLaunchConfig,
    VncLoopbackBindAndRfbauthHardeningFacade,
    VncSecurityAuditViolation,
)

from app.schemas.vnc_hardening import (
    AuditRawVncCommandRequestDTO,
    EvaluatePasswordRequestDTO,
    EvaluatePasswordResponseDTO,
    GenerateSecurePasswordRequestDTO,
    GenerateSecurePasswordResponseDTO,
    SanitizeVncLaunchConfigRequestDTO,
    VncHardenedLaunchSpecDTO,
    VncHardeningAuditReportDTO,
    VncSecurityAuditViolationDTO,
)

logger = logging.getLogger(__name__)


class VncHardeningService:
    """Service mediating VNC loopback bind enforcement, parameter sanitization, and rfbauth auditing."""

    def __init__(
        self,
        facade: VncLoopbackBindAndRfbauthHardeningFacade | None = None,
    ) -> None:
        self._facade = facade or VncLoopbackBindAndRfbauthHardeningFacade()

    @staticmethod
    def _to_violation_dto(v: VncSecurityAuditViolation) -> VncSecurityAuditViolationDTO:
        return VncSecurityAuditViolationDTO(
            violation_type=v.violation_type.value,
            description=v.description,
            flag_or_path=v.flag_or_path,
            auto_remediated=v.auto_remediated,
        )

    @staticmethod
    def _to_spec_dto(spec: VncHardenedLaunchSpec) -> VncHardenedLaunchSpecDTO:
        return VncHardenedLaunchSpecDTO(
            command_args=list(spec.command_args),
            effective_bind_mode=spec.effective_bind_mode.value,
            rfbauth_path=spec.rfbauth_path,
            violations=[VncHardeningService._to_violation_dto(v) for v in spec.violations],
            is_hardened=spec.is_hardened,
        )

    @staticmethod
    def _to_report_dto(report: VncHardeningAuditReport) -> VncHardeningAuditReportDTO:
        return VncHardeningAuditReportDTO(
            timestamp=report.timestamp,
            spec=VncHardeningService._to_spec_dto(report.spec),
            verdict=report.verdict,
            remediation_summary=list(report.remediation_summary),
        )

    def sanitize_launch_config(
        self, request: SanitizeVncLaunchConfigRequestDTO
    ) -> VncHardenedLaunchSpecDTO:
        """Sanitize x11vnc configuration, strip conflicting -nopw, and enforce -localhost by default."""
        bind_mode = (
            VncBindMode.NON_LOOPBACK_OPT_IN
            if request.bind_mode == VncBindMode.NON_LOOPBACK_OPT_IN.value
            else VncBindMode.LOOPBACK
        )
        config = VncLaunchConfig(
            display_num=request.display_num,
            vnc_port=request.vnc_port,
            passwd_file=request.passwd_file,
            bind_mode=bind_mode,
            non_loopback_opt_in=request.non_loopback_opt_in,
            opt_in_password=request.opt_in_password,
            extra_flags=request.extra_flags,
        )
        spec = self._facade.sanitize_launch_config(
            config=config,
            auto_remediate=request.auto_remediate,
        )
        logger.info(
            "Synthesized hardened VNC launch spec for display :%d on port %d (mode=%s, violations=%d)",
            config.display_num,
            config.vnc_port,
            spec.effective_bind_mode.value,
            len(spec.violations),
        )
        return self._to_spec_dto(spec)

    def audit_raw_command(
        self, request: AuditRawVncCommandRequestDTO
    ) -> VncHardeningAuditReportDTO:
        """Audit an existing x11vnc command line argument sequence."""
        report = self._facade.audit_raw_command(request.command_args)
        logger.info(
            "Audited raw VNC command line with %d args; verdict=%s",
            len(request.command_args),
            report.verdict,
        )
        return self._to_report_dto(report)

    def generate_secure_password(
        self, request: GenerateSecurePasswordRequestDTO
    ) -> GenerateSecurePasswordResponseDTO:
        """Generate high-entropy random password suitable for VNC authentication."""
        pwd = self._facade.generate_secure_vnc_password(request.length)
        return GenerateSecurePasswordResponseDTO(
            password=pwd,
            meets_policy=True,
        )

    def evaluate_password(
        self, request: EvaluatePasswordRequestDTO
    ) -> EvaluatePasswordResponseDTO:
        """Verify whether candidate password meets complexity requirements."""
        is_valid, reason = self._facade.evaluate_password(request.password)
        return EvaluatePasswordResponseDTO(
            is_valid=is_valid,
            reason=reason,
        )


_global_service: VncHardeningService | None = None


def get_vnc_hardening_service() -> VncHardeningService:
    """Dependency provider for VncHardeningService."""
    global _global_service
    if _global_service is None:
        _global_service = VncHardeningService()
    return _global_service
