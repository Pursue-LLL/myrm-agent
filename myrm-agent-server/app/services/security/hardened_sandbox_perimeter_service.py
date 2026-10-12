"""
[POS] app/services/security/hardened_sandbox_perimeter_service.py
[INPUT] myrm_agent_harness.core.security.hardened_sandbox_perimeter, app.schemas.hardened_sandbox_perimeter
[OUTPUT] HardenedSandboxPerimeterService, get_hardened_sandbox_perimeter_service

Thread-safe service managing scale-ready hardened sandbox container/microVM validation,
zero-trust outbound egress filtering with anti-SSRF protections, out-of-band ephemeral
credential brokering, and cgroups v2 resource monitoring / fork-bomb mitigation.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.hardened_sandbox_perimeter import (
    EgressTarget,
    HardenedSandboxPerimeterSuite,
    ProcessUsageSnapshot,
)
from myrm_agent_harness.core.security.hardened_sandbox_perimeter import (
    HardenedSandboxSpec as HarnessSandboxSpec,
)
from myrm_agent_harness.core.security.hardened_sandbox_perimeter import (
    SandboxIsolationModeEnum as HarnessIsolationMode,
)

from app.schemas.hardened_sandbox_perimeter import (
    CredentialTicketMintRequest,
    CredentialTicketMintResponse,
    CredentialTicketVerifyRequest,
    CredentialTicketVerifyResponse,
    EgressEvaluateRequest,
    EgressEvaluateResponse,
    EgressVerdictEnum,
    HardenedSandboxSpecRequest,
    ProcessUsageEvaluateRequest,
    ProcessUsageEvaluateResponse,
    RuntimeSpecValidationResponse,
    RuntimeSpecValidationVerdictEnum,
    SandboxSafetyMetricsResponse,
)


class HardenedSandboxPerimeterService:
    """Service providing multi-layered defense-in-depth isolation for agent sandboxes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suite = HardenedSandboxPerimeterSuite()

    def validate_runtime_spec(
        self, req: HardenedSandboxSpecRequest
    ) -> RuntimeSpecValidationResponse:
        """Validate proposed sandbox runtime spec against production hardening standards."""
        harness_mode = HarnessIsolationMode(req.isolation_mode.value)
        harness_spec = HarnessSandboxSpec(
            isolation_mode=harness_mode,
            is_non_root=req.is_non_root,
            uid=req.uid,
            gid=req.gid,
            read_only_rootfs=req.read_only_rootfs,
            tmpfs_noexec=req.tmpfs_noexec,
            persistent_volume_path=req.persistent_volume_path,
            memory_limit_mb=req.memory_limit_mb,
            cpu_quota_pct=req.cpu_quota_pct,
            pids_max=req.pids_max,
        )

        with self._lock:
            res = self._suite.validate_runtime_spec(harness_spec)

        verdict_val = RuntimeSpecValidationVerdictEnum(res.verdict.value)
        return RuntimeSpecValidationResponse(
            is_valid=res.is_valid,
            verdict=verdict_val,
            violations=res.violations,
        )

    def evaluate_egress(self, req: EgressEvaluateRequest) -> EgressEvaluateResponse:
        """Evaluate outbound connection request to intercept SSRF and unauthorized targets."""
        target = EgressTarget(
            host=req.host,
            port=req.port,
            scheme=req.scheme,
        )

        with self._lock:
            res = self._suite.evaluate_egress(
                target=target,
                allowlisted_domains=req.allowlisted_domains,
            )

        verdict_val = EgressVerdictEnum(res.verdict.value)
        return EgressEvaluateResponse(
            is_allowed=res.is_allowed,
            verdict=verdict_val,
            reason=res.reason,
            resolved_ip=res.resolved_ip,
        )

    def register_master_secret(self, secret_alias: str, secret_value: str) -> None:
        """Register host master secret into credential broker."""
        with self._lock:
            self._suite.register_secret(secret_alias, secret_value)

    def mint_credential_ticket(
        self, req: CredentialTicketMintRequest
    ) -> CredentialTicketMintResponse:
        """Mint a short-lived capability ticket without exposing plaintext credentials."""
        with self._lock:
            ticket = self._suite.mint_ephemeral_ticket(
                secret_alias=req.secret_alias,
                allowed_scopes=req.allowed_scopes,
                ttl_seconds=req.ttl_seconds,
            )

        return CredentialTicketMintResponse(
            ticket_id=ticket.ticket_id,
            secret_alias=ticket.secret_alias,
            ephemeral_token=ticket.ephemeral_token,
            expires_at=ticket.expires_at,
            allowed_scopes=ticket.allowed_scopes,
        )

    def verify_credential_ticket(
        self, req: CredentialTicketVerifyRequest
    ) -> CredentialTicketVerifyResponse:
        """Verify ticket validity and authorization scope."""
        with self._lock:
            is_valid = self._suite.verify_ticket(
                ticket_id=req.ticket_id,
                required_scope=req.required_scope,
            )

        return CredentialTicketVerifyResponse(
            is_valid=is_valid,
            ticket_id=req.ticket_id,
        )

    def evaluate_process_usage(
        self, req: ProcessUsageEvaluateRequest
    ) -> ProcessUsageEvaluateResponse:
        """Assess process hierarchy and resource metrics to prevent fork-bombs and OOM."""
        snapshot = ProcessUsageSnapshot(
            active_pids_count=req.active_pids_count,
            memory_used_mb=req.memory_used_mb,
            cpu_percent=req.cpu_percent,
        )

        with self._lock:
            is_safe, msg = self._suite.evaluate_process_usage(
                agent_id=req.agent_id,
                snapshot=snapshot,
                pids_max=req.pids_max,
                memory_limit_mb=req.memory_limit_mb,
            )
            is_tripped = self._suite.is_process_guard_tripped(req.agent_id)

        return ProcessUsageEvaluateResponse(
            is_safe=is_safe,
            agent_id=req.agent_id,
            message=msg,
            is_circuit_broken=is_tripped,
        )

    def reset_process_guard(self, agent_id: str) -> bool:
        """Reset tripped circuit breaker for an agent sandbox."""
        with self._lock:
            return self._suite.reset_process_guard(agent_id)

    def get_metrics(self) -> SandboxSafetyMetricsResponse:
        """Retrieve telemetry snapshot of sandbox security metrics."""
        with self._lock:
            m = self._suite.get_metrics()

        return SandboxSafetyMetricsResponse(
            total_spec_validations=m.total_spec_validations,
            spec_validation_failures=m.spec_validation_failures,
            egress_requests_evaluated=m.egress_requests_evaluated,
            ssrf_blocks=m.ssrf_blocks,
            credential_tickets_minted=m.credential_tickets_minted,
            fork_bomb_mitigations=m.fork_bomb_mitigations,
        )


_SERVICE_INSTANCE: Optional[HardenedSandboxPerimeterService] = None
_SERVICE_LOCK = threading.Lock()


def get_hardened_sandbox_perimeter_service() -> HardenedSandboxPerimeterService:
    """Get singleton instance of HardenedSandboxPerimeterService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = HardenedSandboxPerimeterService()
        return _SERVICE_INSTANCE
