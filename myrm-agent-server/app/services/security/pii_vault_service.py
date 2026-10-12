"""Service orchestrating Client-Side PII Auto-Sanitization and Local Mapping Vault.

[INPUT]
- SanitizePiiRequest, DesanitizePiiRequest, DetectPiiRequest
- Harness PiiEntityDetector, LocalPiiMappingVault, PiiTransformer

[OUTPUT]
- PiiVaultService: enterprise service handling client-side privacy preservation and reversible pseudonymization.

[POS]
Server service layer. Protects user identity and financial PII before sending to external LLM providers.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.pii_vault import (
    LocalPiiMappingVault,
    PiiEntityDetector,
    PiiEntityMatch,
    PiiTransformer,
)

from app.schemas.pii_vault import (
    ClearPiiSessionResponse,
    DesanitizePiiRequest,
    DesanitizePiiResponse,
    DetectPiiRequest,
    DetectPiiResponse,
    PiiEntityMatchDto,
    SanitizePiiRequest,
    SanitizePiiResponse,
)

logger = logging.getLogger(__name__)


def _match_to_dto(domain: PiiEntityMatch) -> PiiEntityMatchDto:
    """Map domain PiiEntityMatch dataclass to Pydantic DTO."""
    return PiiEntityMatchDto(
        entity_type=str(domain.entity_type),
        raw_value=domain.raw_value,
        placeholder=domain.placeholder,
        start_idx=domain.start_idx,
        end_idx=domain.end_idx,
    )


class PiiVaultService:
    """Singleton service for transparent PII pseudonymization and local vault reconstruction."""

    def __init__(self, vault: LocalPiiMappingVault | None = None) -> None:
        self._vault = vault or LocalPiiMappingVault()

    @property
    def vault(self) -> LocalPiiMappingVault:
        """Underlying local mapping vault."""
        return self._vault

    def sanitize_text(self, request: SanitizePiiRequest) -> SanitizePiiResponse:
        """Scan text, replace sensitive PII with consistent placeholders, and record in vault."""
        result = PiiTransformer.pseudonymize(
            text=request.text,
            session_id=request.session_id,
            vault=self._vault,
        )
        return SanitizePiiResponse(
            sanitized_text=result.sanitized_text,
            placeholders_count=result.placeholders_count,
            entities_detected=[_match_to_dto(m) for m in result.entities_detected],
            session_id=result.session_id,
            sanitized_at=result.sanitized_at,
        )

    def desanitize_text(self, request: DesanitizePiiRequest) -> DesanitizePiiResponse:
        """Reverse replace placeholders back to original PII using the session's local vault."""
        result = PiiTransformer.desanitize(
            text=request.text,
            session_id=request.session_id,
            vault=self._vault,
        )
        return DesanitizePiiResponse(
            restored_text=result.restored_text,
            restored_count=result.restored_count,
            placeholders_found=list(result.placeholders_found),
            session_id=result.session_id,
            restored_at=result.restored_at,
        )

    def detect_pii(self, request: DetectPiiRequest) -> DetectPiiResponse:
        """Scan text and return detected PII entities without modifying content."""
        matches = PiiEntityDetector.detect_entities(request.text)
        return DetectPiiResponse(
            matches=[_match_to_dto(m) for m in matches],
            count=len(matches),
        )

    def clear_session(self, session_id: str) -> ClearPiiSessionResponse:
        """Securely wipe all local PII mappings for the specified session."""
        self._vault.clear_session(session_id)
        return ClearPiiSessionResponse(
            session_id=session_id,
            cleared=True,
            message=f"PII mappings for session '{session_id}' have been purged",
        )


# Global singleton instance
default_pii_vault_service = PiiVaultService()
