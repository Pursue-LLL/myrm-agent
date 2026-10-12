"""REST API for Client-Side Secret Leak Scanning and BFF Auto-Refactor Diagnostics.

[POS]
Provides endpoints for:
1. Scanning client-side source code (.tsx, .jsx, .vue, .html, .js) for hardcoded secrets.
2. Generating surgical BFF refactoring artifacts (extracted .env, server proxy route, remediated client code).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.security.client_secret_guard import (
    BffRefactorResponseSchema,
    ClientSecretGuardService,
    ClientSecretScanReport,
)

router = APIRouter(prefix="/client-secrets", tags=["security-client-secrets"])


class ScanClientCodeRequest(BaseModel):
    """Payload to trigger secret scanning on client code."""

    code: str = Field(..., description="Source code content to inspect")
    file_path: str = Field(..., description="Relative or absolute file path of the source code")


class RefactorToBffRequest(BaseModel):
    """Payload to generate BFF refactoring suggestions."""

    code: str = Field(..., description="Source code containing detected or suspected secrets")
    file_path: str = Field(..., description="Target file path of the client component")


@router.post("/scan", response_model=ClientSecretScanReport)
async def scan_client_code(payload: ScanClientCodeRequest) -> ClientSecretScanReport:
    """Scan browser-facing code for hardcoded API keys, tokens, and credentials."""
    return ClientSecretGuardService.scan_client_code(
        code=payload.code,
        file_path=payload.file_path,
    )


@router.post("/refactor-bff", response_model=BffRefactorResponseSchema)
async def refactor_to_bff(payload: RefactorToBffRequest) -> BffRefactorResponseSchema:
    """Generate automated BFF refactoring patch: .env extract, server proxy route, and safe client fetch."""
    return ClientSecretGuardService.refactor_to_bff(
        code=payload.code,
        file_path=payload.file_path,
    )
