"""API router for Client-Side PII Auto-Sanitization and Local Mapping Vault.

[INPUT]
- SanitizePiiRequest, DesanitizePiiRequest, DetectPiiRequest, session_id path param

[OUTPUT]
- SanitizePiiResponse, DesanitizePiiResponse, DetectPiiResponse, ClearPiiSessionResponse

[POS]
Server API layer. Exposes REST endpoints for client-side privacy preservation and reversible pseudonymization.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.pii_vault import (
    ClearPiiSessionResponse,
    DesanitizePiiRequest,
    DesanitizePiiResponse,
    DetectPiiRequest,
    DetectPiiResponse,
    SanitizePiiRequest,
    SanitizePiiResponse,
)
from app.services.security.pii_vault_service import default_pii_vault_service

router = APIRouter(prefix="/pii-vault", tags=["pii-vault"])


@router.post("/sanitize", response_model=SanitizePiiResponse)
async def sanitize_text(
    request: SanitizePiiRequest,
) -> SanitizePiiResponse:
    """Scan text, replace sensitive PII with placeholders, and save mapping to local vault."""
    return default_pii_vault_service.sanitize_text(request)


@router.post("/desanitize", response_model=DesanitizePiiResponse)
async def desanitize_text(
    request: DesanitizePiiRequest,
) -> DesanitizePiiResponse:
    """Reverse-replace placeholders back to original PII using the session's local vault."""
    return default_pii_vault_service.desanitize_text(request)


@router.post("/detect", response_model=DetectPiiResponse)
async def detect_pii(
    request: DetectPiiRequest,
) -> DetectPiiResponse:
    """Scan text and return detected PII entities without modifying content."""
    return default_pii_vault_service.detect_pii(request)


@router.delete("/session/{session_id}", response_model=ClearPiiSessionResponse)
async def clear_session_pii_vault(
    session_id: str,
) -> ClearPiiSessionResponse:
    """Securely purge all local PII mappings for the specified session."""
    return default_pii_vault_service.clear_session(session_id)
