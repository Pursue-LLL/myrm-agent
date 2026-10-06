"""Service layer for Muse-Style Secure VM Isolation and Sentinel Suite.

[INPUT]
- Harness MuseSecureVmManager and schema request DTOs.

[OUTPUT]
- MuseSentinelIsolationService managing secure VM lifecycle, tokens, and traffic inspection.

[POS]
Service layer bridging HTTP presentation with harness muse secure VM isolation.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.muse_sentinel_isolation import (
    MuseSecureVmManager,
    OutboundTrafficPayload,
    SandboxIsolationTier,
    SecureVmProfile,
    SentinelReviewResult,
    SingleUseToken,
    TokenRedemptionResult,
    TokenType,
)

from app.schemas.muse_sentinel_isolation import (
    IssueSingleUseTokenRequest,
    RedeemSingleUseTokenRequest,
    RegisterVmRequest,
    ReviewOutboundTrafficRequest,
    SecureVmProfileResponse,
    SentinelReviewResultResponse,
    SingleUseTokenResponse,
    TokenRedemptionResultResponse,
)

logger = logging.getLogger(__name__)


class MuseSentinelIsolationService:
    """Coordinates user-dedicated VM descriptors, pre-outbound Sentinel, and single-use credentials."""

    def __init__(self, manager: MuseSecureVmManager | None = None) -> None:
        self.manager = manager or MuseSecureVmManager()

    def register_vm(self, req: RegisterVmRequest) -> SecureVmProfileResponse:
        """Provision or register a dedicated secure sandbox environment for a user."""
        tier = SandboxIsolationTier(req.isolation_tier.lower())
        profile = self.manager.register_vm(
            user_id=req.user_id,
            isolation_tier=tier,
            volume_mount=req.volume_mount,
        )
        logger.info(
            "Registered dedicated secure VM '%s' for user '%s' (tier: %s)",
            profile.vm_id,
            profile.user_id,
            profile.isolation_tier,
        )
        return self._convert_profile(profile)

    def get_vm(self, vm_id: str) -> SecureVmProfileResponse | None:
        """Lookup VM by vm_id."""
        profile = self.manager.get_vm(vm_id)
        if profile is None:
            return None
        return self._convert_profile(profile)

    def get_user_vm(self, user_id: str) -> SecureVmProfileResponse | None:
        """Lookup VM by user_id."""
        profile = self.manager.get_user_vm(user_id)
        if profile is None:
            return None
        return self._convert_profile(profile)

    def list_vms(self) -> list[SecureVmProfileResponse]:
        """List all active VM profiles."""
        return [self._convert_profile(p) for p in self.manager.list_vms()]

    def review_outbound(
        self, req: ReviewOutboundTrafficRequest
    ) -> SentinelReviewResultResponse:
        """Screen an outbound traffic frame with Sentinel before egress."""
        payload = OutboundTrafficPayload(
            request_id=req.request_id,
            destination_url=req.destination_url,
            method=req.method,
            headers=req.headers,
            body_preview=req.body_preview,
            source_vm_id=req.source_vm_id,
        )
        result = self.manager.review_outbound(payload)
        if result.verdict != "allow":
            logger.warning(
                "Sentinel flagged outbound traffic [req_id=%s, verdict=%s, rule=%s]: %s",
                result.request_id,
                result.verdict,
                result.matched_rule,
                result.reason,
            )
        return self._convert_review(result)

    def issue_single_use_token(
        self, req: IssueSingleUseTokenRequest
    ) -> SingleUseTokenResponse:
        """Issue an isolated ephemeral single-use token or virtual payment card."""
        token_type = TokenType(req.token_type.lower())
        token = self.manager.issue_single_use_credential(
            token_type=token_type,
            max_amount=req.max_amount,
            currency=req.currency,
            bound_recipient=req.bound_recipient,
            ttl_seconds=req.ttl_seconds,
        )
        logger.info(
            "Issued single-use token '%s' (type: %s, max_amount: %.2f %s, recipient: %s)",
            token.token_id,
            token.token_type,
            token.max_amount,
            token.currency,
            token.bound_recipient,
        )
        return self._convert_token(token)

    def redeem_single_use_token(
        self, req: RedeemSingleUseTokenRequest
    ) -> TokenRedemptionResultResponse:
        """Redeem and burn a single-use token."""
        result = self.manager.redeem_single_use_credential(
            virtual_token=req.virtual_token,
            amount=req.amount,
            currency=req.currency,
            recipient=req.recipient,
        )
        if not result.success:
            logger.warning(
                "Failed single-use token redemption attempt [token_id=%s]: %s",
                result.token_id,
                result.reason,
            )
        return self._convert_redemption(result)

    def list_active_tokens(self) -> list[SingleUseTokenResponse]:
        """List active unconsumed, unexpired tokens."""
        tokens = self.manager.proxy.list_tokens(active_only=True)
        return [self._convert_token(t) for t in tokens]

    @staticmethod
    def _convert_profile(p: SecureVmProfile) -> SecureVmProfileResponse:
        return SecureVmProfileResponse(
            vm_id=p.vm_id,
            user_id=p.user_id,
            isolation_tier=p.isolation_tier.value,
            volume_mount=p.volume_mount,
            egress_mode=p.egress_mode,
            credential_sealed=p.credential_sealed,
            created_at=p.created_at,
        )

    @staticmethod
    def _convert_review(r: SentinelReviewResult) -> SentinelReviewResultResponse:
        return SentinelReviewResultResponse(
            request_id=r.request_id,
            verdict=r.verdict.value,
            matched_rule=r.matched_rule,
            reason=r.reason,
            risk_score=r.risk_score,
            timestamp=r.timestamp,
        )

    @staticmethod
    def _convert_token(t: SingleUseToken) -> SingleUseTokenResponse:
        return SingleUseTokenResponse(
            token_id=t.token_id,
            virtual_token=t.virtual_token,
            token_type=t.token_type.value,
            max_amount=t.max_amount,
            currency=t.currency,
            bound_recipient=t.bound_recipient,
            is_consumed=t.is_consumed,
            expires_at=t.expires_at,
            created_at=t.created_at,
        )

    @staticmethod
    def _convert_redemption(r: TokenRedemptionResult) -> TokenRedemptionResultResponse:
        return TokenRedemptionResultResponse(
            token_id=r.token_id,
            success=r.success,
            reason=r.reason,
            timestamp=r.timestamp,
        )


_service_instance: MuseSentinelIsolationService | None = None


def get_muse_sentinel_isolation_service() -> MuseSentinelIsolationService:
    """FastAPI dependency provider for MuseSentinelIsolationService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = MuseSentinelIsolationService()
    return _service_instance


def reset_muse_sentinel_isolation_service() -> None:
    """Reset singleton instance (useful for testing)."""
    global _service_instance
    _service_instance = None
