"""Service layer for Dual-Tier Root Admin & User API Key Isolation Suite.

[INPUT]
- RegisterAdminKeyRequest, DeriveUserKeyRequest, EvaluateAccessRequest DTOs.

[OUTPUT]
- RegisterAdminKeyResponseDto, DeriveUserKeyResponseDto, EvaluateAccessResponseDto.

[POS]
- Server service wrapping harness DualTierKeyVault and DualTierIsolationGate.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.dual_tier_isolation.isolation_gate import (
    DualTierIsolationGate,
)
from myrm_agent_harness.core.security.dual_tier_isolation.key_vault import (
    DualTierKeyVault,
)
from myrm_agent_harness.core.security.dual_tier_isolation.types import (
    AccessPlane,
)

from app.schemas.dual_tier_isolation import (
    DeriveUserKeyRequest,
    DeriveUserKeyResponseDto,
    EvaluateAccessRequest,
    EvaluateAccessResponseDto,
    RegisterAdminKeyRequest,
    RegisterAdminKeyResponseDto,
)


class DualTierIsolationService:
    """Coordinates key generation and dual-tier isolation gate verification."""

    def __init__(
        self,
        key_vault: DualTierKeyVault | None = None,
        isolation_gate: DualTierIsolationGate | None = None,
    ) -> None:
        self._vault = key_vault or DualTierKeyVault()
        self._gate = isolation_gate or DualTierIsolationGate(self._vault)

    def register_admin_key(
        self, request: RegisterAdminKeyRequest
    ) -> RegisterAdminKeyResponseDto:
        """Register a Root Admin key for control-plane management."""
        raw_key, record = self._vault.register_root_admin_key(
            allowed_scopes=request.allowed_scopes,
            custom_raw_key=request.custom_raw_key,
        )

        return RegisterAdminKeyResponseDto(
            key_id=record.key_id,
            raw_key=raw_key,
            tier=record.tier.value,
            allowed_scopes=list(record.allowed_scopes),
        )

    def derive_user_key(
        self, request: DeriveUserKeyRequest
    ) -> DeriveUserKeyResponseDto:
        """Derive an isolated User API key bound to a tenant/user context."""
        raw_key, record = self._vault.derive_user_key(
            user_id=request.user_id,
            tenant_id=request.tenant_id,
            agent_id=request.agent_id,
            allowed_scopes=request.allowed_scopes,
        )

        return DeriveUserKeyResponseDto(
            key_id=record.key_id,
            raw_key=raw_key,
            tier=record.tier.value,
            user_id=record.user_id or "",
            tenant_id=record.tenant_id or "",
            agent_id=record.agent_id,
            allowed_scopes=list(record.allowed_scopes),
        )

    def evaluate_access(
        self, request: EvaluateAccessRequest
    ) -> EvaluateAccessResponseDto:
        """Verify access permission against the dual-tier physical gate."""
        plane = (
            AccessPlane.CONTROL_PLANE
            if request.requested_plane.upper() == "CONTROL_PLANE"
            else AccessPlane.DATA_PLANE
        )

        verdict = self._gate.evaluate_access(
            raw_key=request.raw_key,
            requested_plane=plane,
            target_user_id=request.target_user_id,
            target_tenant_id=request.target_tenant_id,
            requested_scope=request.requested_scope,
        )

        tier_val = verdict.effective_tier.value if verdict.effective_tier else None

        return EvaluateAccessResponseDto(
            verdict=verdict.verdict.value,
            is_permitted=verdict.is_permitted,
            effective_tier=tier_val,
            user_id=verdict.user_id,
            tenant_id=verdict.tenant_id,
            audit_id=verdict.audit_id,
            message=verdict.message,
        )

    def revoke_key(self, key_id: str) -> bool:
        """Revoke key by ID."""
        return self._vault.revoke_key(key_id)


_default_service: DualTierIsolationService | None = None


def get_dual_tier_isolation_service() -> DualTierIsolationService:
    """Singleton provider for DualTierIsolationService."""
    global _default_service
    if _default_service is None:
        _default_service = DualTierIsolationService()
    return _default_service
