"""
[POS] app/services/security/media_artifact_grants_service.py
[INPUT] app.schemas.media_artifact_grants, myrm_agent_harness.core.security.media_artifact_grants
[OUTPUT] MediaArtifactGrantsService, get_media_artifact_grants_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.media_artifact_grants import (
    MediaArtifactGrant,
    MediaArtifactRoleScopedGrantsFacade,
    ProducerRole,
)

from app.schemas.media_artifact_grants import (
    EvaluateGrantRequestDTO,
    GrantEvaluationResponseDTO,
    MediaArtifactGrantMetricsDTO,
    MediaArtifactGrantResponseDTO,
    RevokeGrantRequestDTO,
    RevokeGrantResponseDTO,
)

logger = logging.getLogger(__name__)


class MediaArtifactGrantsService:
    """Service mediating role-scoped artifact evaluation and inline display authorization."""

    def __init__(
        self, facade: MediaArtifactRoleScopedGrantsFacade | None = None
    ) -> None:
        self._facade = facade or MediaArtifactRoleScopedGrantsFacade()

    def evaluate_and_grant(
        self, request: EvaluateGrantRequestDTO
    ) -> GrantEvaluationResponseDTO:
        """Evaluate artifact inline presentation eligibility based on producer role."""
        try:
            role = ProducerRole(request.producer_role.upper())
        except ValueError:
            logger.warning("Unrecognized producer role: %s, defaulting to EXTERNAL_UNTRUSTED", request.producer_role)
            role = ProducerRole.EXTERNAL_UNTRUSTED

        result = self._facade.evaluate_and_grant(
            session_id=request.session_id,
            artifact_id=request.artifact_id,
            producer_role=role,
            mime_type=request.mime_type,
            checksum_sha256=request.checksum_sha256,
            metadata=request.metadata,
        )

        return GrantEvaluationResponseDTO(
            is_allowed=result.is_allowed,
            grant_status=result.grant_status.value,
            rendered_preview_mode=result.rendered_preview_mode,
            diagnostic_reason=result.diagnostic_reason,
            artifact_id=result.artifact_id,
            session_id=result.session_id,
        )

    def revoke_grant(
        self, request: RevokeGrantRequestDTO
    ) -> RevokeGrantResponseDTO:
        """Revoke active inline render grant for an artifact."""
        success = self._facade.revoke_grant(
            session_id=request.session_id,
            artifact_id=request.artifact_id,
            reason=request.reason,
        )
        return RevokeGrantResponseDTO(
            session_id=request.session_id,
            artifact_id=request.artifact_id,
            revoked=success,
            reason=request.reason,
        )

    def get_grant(
        self, session_id: str, artifact_id: str
    ) -> MediaArtifactGrantResponseDTO | None:
        """Fetch grant status for a specific artifact."""
        grant = self._facade.get_grant(session_id=session_id, artifact_id=artifact_id)
        if grant is None:
            return None
        return self._to_grant_dto(grant)

    def list_grants_for_session(
        self, session_id: str
    ) -> list[MediaArtifactGrantResponseDTO]:
        """Fetch all artifact grants belonging to a session."""
        grants = self._facade.list_grants_for_session(session_id=session_id)
        return [self._to_grant_dto(g) for g in grants]

    def get_metrics(self) -> MediaArtifactGrantMetricsDTO:
        """Retrieve operational metric counters."""
        m = self._facade.metrics
        return MediaArtifactGrantMetricsDTO(
            grants_evaluated_total=m.grants_evaluated_total,
            inline_granted_total=m.inline_granted_total,
            external_blocked_total=m.external_blocked_total,
            grants_revoked_total=m.grants_revoked_total,
        )

    @staticmethod
    def _to_grant_dto(grant: MediaArtifactGrant) -> MediaArtifactGrantResponseDTO:
        return MediaArtifactGrantResponseDTO(
            artifact_id=grant.artifact_id,
            session_id=grant.session_id,
            producer_role=grant.producer_role.value,
            mime_type=grant.mime_type,
            is_inline_allowed=grant.is_inline_allowed,
            grant_status=grant.grant_status.value,
            granted_at_epoch=grant.granted_at_epoch,
            checksum_sha256=grant.checksum_sha256,
            metadata=dict(grant.metadata),
        )


_global_service: MediaArtifactGrantsService | None = None


def get_media_artifact_grants_service() -> MediaArtifactGrantsService:
    """Singleton provider for MediaArtifactGrantsService."""
    global _global_service
    if _global_service is None:
        _global_service = MediaArtifactGrantsService()
    return _global_service
