"""REST API for Zero-Trust Credential Isolation and Git Leakage Shield.

[INPUT]
- DTO schemas from app.schemas.git_leak_shield
- GitLeakShieldService from app.services.security.git_leak_shield_service

[OUTPUT]
- APIRouter mounted under /security/git-shield

[POS]
Server API. Provides endpoints for inspecting Git diffs before commit/push,
blocking leaking Git operations, and scrubbing credentials from egress logs.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.git_leak_shield import (
    GitDiffScanRequest,
    GitDiffScanResponse,
    PreCommitCheckRequest,
    PreCommitCheckResponse,
    RedactTextRequest,
    RedactTextResponse,
)
from app.services.security.git_leak_shield_service import (
    get_git_leak_shield_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/git-shield", tags=["security-git-shield"])


@router.post(
    "/scan-diff",
    response_model=GitDiffScanResponse,
    summary="Scan unified git diff for credential leaks",
)
async def scan_git_diff(body: GitDiffScanRequest) -> GitDiffScanResponse:
    """Inspect added lines in a git diff to prevent accidental credential staging."""
    service = get_git_leak_shield_service()
    return service.scan_diff(body)


@router.post(
    "/check-commit",
    response_model=PreCommitCheckResponse,
    summary="Validate whether a git commit/push command is safe",
)
async def check_commit_command(body: PreCommitCheckRequest) -> PreCommitCheckResponse:
    """Verify git commit or push command and block execution if secrets are staged."""
    service = get_git_leak_shield_service()
    return service.check_commit_command(body)


@router.post(
    "/redact",
    response_model=RedactTextResponse,
    summary="Scrub sensitive credentials from outbound text or logs",
)
async def redact_egress_text(body: RedactTextRequest) -> RedactTextResponse:
    """Redact API keys and tokens from outbound text or agent transcripts."""
    service = get_git_leak_shield_service()
    return service.redact_egress_text(body)
