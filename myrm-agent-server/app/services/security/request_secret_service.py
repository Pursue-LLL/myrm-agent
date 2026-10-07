"""
[POS] app/services/security/request_secret_service.py
[INPUT] app.schemas.request_secret, myrm_agent_harness.core.security.request_secret
[OUTPUT] RequestSecretService, get_request_secret_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.request_secret import (
    MaskedCredentialRef,
    RequestSecretMaskedCredentialCardFacade,
    SanitizedSecretResult,
    SecretCardSession,
    SecretInputSubmission,
    SecretRequestIntent,
)

from app.schemas.request_secret import (
    CreateSecretCardRequestDTO,
    FulfillSecretCardRequestDTO,
    MaskedCredentialRefDTO,
    RegisterSavedCredentialRequestDTO,
    RejectSecretCardRequestDTO,
    SanitizedSecretResultDTO,
    SecretCardSessionDTO,
    SecretRequestIntentDTO,
)

logger = logging.getLogger(__name__)


class RequestSecretService:
    """Service mediating request_secret interactive cards, masked backfills, and safe storage."""

    def __init__(
        self,
        facade: RequestSecretMaskedCredentialCardFacade | None = None,
    ) -> None:
        self._facade = facade or RequestSecretMaskedCredentialCardFacade()

    @staticmethod
    def _to_ref_dto(r: MaskedCredentialRef | None) -> MaskedCredentialRefDTO | None:
        if r is None:
            return None
        return MaskedCredentialRefDTO(
            credential_id=r.credential_id,
            target_system=r.target_system,
            mask_preview=r.mask_preview,
            created_at=r.created_at,
        )

    @staticmethod
    def _to_intent_dto(i: SecretRequestIntent) -> SecretRequestIntentDTO:
        return SecretRequestIntentDTO(
            target_system=i.target_system,
            purpose_description=i.purpose_description,
            scope=i.scope,
            ttl_seconds=i.ttl_seconds,
        )

    @staticmethod
    def _to_session_dto(s: SecretCardSession) -> SecretCardSessionDTO:
        return SecretCardSessionDTO(
            card_id=s.card_id,
            agent_id=s.agent_id,
            task_id=s.task_id,
            intent=RequestSecretService._to_intent_dto(s.intent),
            status=s.status.value,
            masked_ref=RequestSecretService._to_ref_dto(s.masked_ref),
            rejection_reason=s.rejection_reason,
            created_at=s.created_at,
            expires_at=s.expires_at,
        )

    @staticmethod
    def _to_result_dto(r: SanitizedSecretResult) -> SanitizedSecretResultDTO:
        return SanitizedSecretResultDTO(
            card_id=r.card_id,
            target_system=r.target_system,
            mask_preview=r.mask_preview,
            is_backfill=r.is_backfill,
            stored_safely=r.stored_safely,
            transcript_safe_summary=r.transcript_safe_summary,
        )

    def create_card_session(
        self, request: CreateSecretCardRequestDTO
    ) -> SecretCardSessionDTO:
        """Create a new pending secret request card session."""
        intent = SecretRequestIntent(
            target_system=request.intent.target_system,
            purpose_description=request.intent.purpose_description,
            scope=request.intent.scope,
            ttl_seconds=request.intent.ttl_seconds,
        )
        session = self._facade.create_secret_request_card(
            agent_id=request.agent_id,
            task_id=request.task_id,
            intent=intent,
        )
        logger.info(
            "Created secret card %s for agent %s on target '%s'",
            session.card_id,
            request.agent_id,
            intent.target_system,
        )
        return self._to_session_dto(session)

    def fulfill_card(
        self, request: FulfillSecretCardRequestDTO
    ) -> SanitizedSecretResultDTO:
        """Fulfill an active card session with plaintext input or saved backfill."""
        submission = SecretInputSubmission(
            raw_secret=request.submission.raw_secret,
            selected_credential_id=request.submission.selected_credential_id,
            extra_metadata=request.submission.extra_metadata,
        )
        result = self._facade.fulfill_secret_request(
            card_id=request.card_id,
            submission=submission,
        )
        logger.info(
            "Fulfilled secret card %s: target=%s, backfill=%s",
            request.card_id,
            result.target_system,
            result.is_backfill,
        )
        return self._to_result_dto(result)

    def reject_card(
        self, request: RejectSecretCardRequestDTO
    ) -> SecretCardSessionDTO:
        """Explicitly reject a secret request card."""
        session = self._facade.reject_secret_request(
            card_id=request.card_id,
            reason=request.reason,
        )
        logger.info("Rejected secret card %s: reason='%s'", request.card_id, request.reason)
        return self._to_session_dto(session)

    def get_card_session(self, card_id: str) -> SecretCardSessionDTO | None:
        """Fetch status and metadata of a secret card session."""
        session = self._facade.get_card_session(card_id)
        if session is None:
            return None
        return self._to_session_dto(session)

    def register_saved_credential(
        self, request: RegisterSavedCredentialRequestDTO
    ) -> MaskedCredentialRefDTO:
        """Register an existing credential in vault and return its safe masked reference."""
        ref = self._facade.register_saved_credential(
            target_system=request.target_system,
            raw_secret=request.raw_secret,
            credential_id=request.credential_id,
        )
        return MaskedCredentialRefDTO(
            credential_id=ref.credential_id,
            target_system=ref.target_system,
            mask_preview=ref.mask_preview,
            created_at=ref.created_at,
        )

    def list_saved_credentials(
        self, target_system: str | None = None
    ) -> list[MaskedCredentialRefDTO]:
        """List safe masked credential references available for backfill."""
        refs = self._facade.list_saved_credentials(target_system=target_system)
        return [
            MaskedCredentialRefDTO(
                credential_id=r.credential_id,
                target_system=r.target_system,
                mask_preview=r.mask_preview,
                created_at=r.created_at,
            )
            for r in refs
        ]


_global_service: RequestSecretService | None = None


def get_request_secret_service() -> RequestSecretService:
    """Dependency provider for RequestSecretService."""
    global _global_service
    if _global_service is None:
        _global_service = RequestSecretService()
    return _global_service
