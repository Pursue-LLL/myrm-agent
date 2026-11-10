"""Credentials management API router.

Endpoints for listing and deleting credential files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.backends.skills.credential_checker import (
    CredentialExpiryChecker,
    ExpiryStatus,
)
from pydantic import BaseModel

from app.api.dependencies import get_workspace_root

logger = logging.getLogger(__name__)

router = APIRouter(tags=["credentials"])

_CREDENTIALS_DIR = ".credentials"


class CredentialFile(BaseModel):
    """Credential file metadata."""

    filename: str
    """Relative path within credentials directory"""

    size: int
    """File size in bytes"""

    expiry_status: str | None = None
    """Expiry status: valid, expiring_soon, expired, error"""

    expiry_message: str | None = None
    """Human-readable expiry message"""

    remaining_days: int | None = None
    """Days until expiry (if applicable)"""


class CredentialListResponse(BaseModel):
    """Response for listing credentials."""

    files: list[CredentialFile]
    """List of credential files"""


@router.get("", response_model=CredentialListResponse)
async def list_credentials(
    workspace_root: Path = Depends(get_workspace_root),
) -> CredentialListResponse:
    """List the credential files with expiry status."""
    credentials_dir = workspace_root / _CREDENTIALS_DIR

    if not credentials_dir.exists():
        return CredentialListResponse(files=[])

    expiry_checker = CredentialExpiryChecker()
    files: list[CredentialFile] = []

    for file_path in credentials_dir.rglob("*"):
        if file_path.is_file():
            relative_path = file_path.relative_to(credentials_dir)

            # Check expiry status
            expiry_result = expiry_checker.check_credential_file(file_path)

            files.append(
                CredentialFile(
                    filename=str(relative_path),
                    size=file_path.stat().st_size,
                    expiry_status=expiry_result.status.value if expiry_result.status != ExpiryStatus.ERROR else None,
                    expiry_message=expiry_result.message,
                    remaining_days=expiry_result.remaining_days,
                )
            )

    return CredentialListResponse(files=files)


@router.delete("/{filename:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(
    filename: str,
    workspace_root: Path = Depends(get_workspace_root),
) -> None:
    """Delete a credential file."""
    # Security: reject absolute paths and path traversal
    if Path(filename).is_absolute() or ".." in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename (absolute paths or '..' not allowed)",
        )

    credentials_dir = workspace_root / _CREDENTIALS_DIR
    target_path = credentials_dir / filename

    # Verify file exists and is within credentials directory
    try:
        resolved = target_path.resolve()
        resolved.relative_to(credentials_dir.resolve())
    except (ValueError, OSError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential file not found",
        ) from None

    if not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Credential file not found",
        ) from None

    try:
        target_path.unlink()
        logger.info("Deleted credential file: %s", filename)
    except Exception as e:
        logger.error("Failed to delete credential file %s: %s", filename, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file",
        ) from e
