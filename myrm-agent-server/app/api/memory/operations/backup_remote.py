"""Remote backup API endpoints.

Provides REST endpoints for managing remote backup sync:
- Check connection
- Trigger manual backup
- List remote backups
- Restore from remote backup
- Configure auto-sync via Omni-Config (backupSync key)
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.memory.backup_remote import (
    S3BackupConfig,
    S3BackupStrategy,
    WebDAVBackupConfig,
    WebDAVBackupStrategy,
)
from app.services.memory.backup_remote_scheduler import (
    restore_from_remote,
    run_remote_backup,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backup/remote")


# ============================================================================
# Request/Response Models
# ============================================================================


class WebDAVConfigRequest(BaseModel):
    """WebDAV connection configuration."""

    host: str = Field(..., description="WebDAV server URL")
    username: str = Field("", description="WebDAV username")
    password: str = Field("", description="WebDAV password")
    path: str = Field("/myrm-backups", description="Remote directory path")


class S3ConfigRequest(BaseModel):
    """S3-compatible storage configuration."""

    endpoint: str = Field(..., description="S3 endpoint URL")
    region: str = Field("", description="AWS region")
    bucket: str = Field(..., description="S3 bucket name")
    access_key_id: str = Field(..., description="Access key ID")
    secret_access_key: str = Field(..., description="Secret access key")
    prefix: str = Field("myrm-backups/", description="Object key prefix")
    force_path_style: bool = Field(True, description="Use path-style addressing")


class RemoteBackupRequest(BaseModel):
    """Request to trigger a remote backup."""

    provider: Literal["webdav", "s3"] = Field(..., description="Storage provider type")
    webdav: WebDAVConfigRequest | None = None
    s3: S3ConfigRequest | None = None
    device_name: str = Field("", description="Device identifier for backup naming")
    max_backups: int = Field(10, ge=1, le=100, description="Max backups to retain per device")


class ConnectionCheckRequest(BaseModel):
    """Request to check remote storage connection."""

    provider: Literal["webdav", "s3"]
    webdav: WebDAVConfigRequest | None = None
    s3: S3ConfigRequest | None = None


class RemoteRestoreRequest(BaseModel):
    """Request to restore from a remote backup."""

    provider: Literal["webdav", "s3"]
    webdav: WebDAVConfigRequest | None = None
    s3: S3ConfigRequest | None = None
    file_name: str = Field(..., description="Remote backup file name to restore")


class RemoteBackupListRequest(BaseModel):
    """Request to list remote backups."""

    provider: Literal["webdav", "s3"]
    webdav: WebDAVConfigRequest | None = None
    s3: S3ConfigRequest | None = None


class RemoteBackupFileResponse(BaseModel):
    """Single remote backup file info."""

    file_name: str
    modified_time: str
    size_bytes: int


class RemoteBackupListResponse(BaseModel):
    """Response for listing remote backups."""

    files: list[RemoteBackupFileResponse]
    total: int


class RemoteBackupResponse(BaseModel):
    """Response for backup/restore operations."""

    success: bool
    file_name: str | None = None
    size_bytes: int | None = None
    restored_count: int | None = None
    duration_ms: float = 0
    error: str | None = None


class ConnectionCheckResponse(BaseModel):
    """Response for connection check."""

    connected: bool
    error: str | None = None


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/check-connection", response_model=ConnectionCheckResponse)
async def check_connection(request: ConnectionCheckRequest) -> ConnectionCheckResponse:
    """Test connectivity to remote storage provider."""
    try:
        strategy = _build_strategy(request.provider, request.webdav, request.s3)
        connected = await strategy.check_connection()
        return ConnectionCheckResponse(connected=connected)
    except ValueError as e:
        return ConnectionCheckResponse(connected=False, error=str(e))
    except Exception as e:
        logger.exception("Connection check failed: %s", e)
        return ConnectionCheckResponse(connected=False, error=str(e))


@router.post("/trigger", response_model=RemoteBackupResponse)
async def trigger_backup(request: RemoteBackupRequest) -> RemoteBackupResponse:
    """Trigger a manual remote backup."""
    import platform

    try:
        strategy = _build_strategy(request.provider, request.webdav, request.s3)
        result = await run_remote_backup(
            strategy=strategy,
            device_name=request.device_name or platform.node(),
            max_backups=request.max_backups,
        )
        return RemoteBackupResponse(
            success=result.get("success", False),
            file_name=result.get("file_name"),
            size_bytes=result.get("size_bytes"),
            duration_ms=result.get("duration_ms", 0),
            error=result.get("error"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Remote backup trigger failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remote backup failed: {e!s}",
        ) from e


@router.post("/list", response_model=RemoteBackupListResponse)
async def list_remote_backups(request: RemoteBackupListRequest) -> RemoteBackupListResponse:
    """List all backup files on remote storage."""
    try:
        strategy = _build_strategy(request.provider, request.webdav, request.s3)
        files = await strategy.list_files()
        return RemoteBackupListResponse(
            files=[
                RemoteBackupFileResponse(
                    file_name=f.file_name,
                    modified_time=f.modified_time.isoformat(),
                    size_bytes=f.size_bytes,
                )
                for f in files
            ],
            total=len(files),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Remote backup list failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list remote backups: {e!s}",
        ) from e


@router.post("/restore", response_model=RemoteBackupResponse)
async def restore_remote_backup(request: RemoteRestoreRequest) -> RemoteBackupResponse:
    """Download and restore a backup from remote storage."""
    try:
        strategy = _build_strategy(request.provider, request.webdav, request.s3)
        result = await restore_from_remote(
            strategy=strategy,
            file_name=request.file_name,
        )
        return RemoteBackupResponse(
            success=result.get("success", False),
            restored_count=result.get("restored_count"),
            duration_ms=result.get("duration_ms", 0),
            error=result.get("error"),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Remote restore failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remote restore failed: {e!s}",
        ) from e


@router.post("/delete")
async def delete_remote_backup(request: RemoteRestoreRequest) -> dict[str, bool]:
    """Delete a backup file from remote storage."""
    try:
        strategy = _build_strategy(request.provider, request.webdav, request.s3)
        success = await strategy.delete(request.file_name)
        return {"success": success}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Remote delete failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remote delete failed: {e!s}",
        ) from e


# ============================================================================
# Helpers
# ============================================================================


def _build_strategy(
    provider: str,
    webdav: WebDAVConfigRequest | None,
    s3: S3ConfigRequest | None,
) -> WebDAVBackupStrategy | S3BackupStrategy:
    """Build the appropriate backup strategy from request params."""
    if provider == "webdav":
        if not webdav:
            raise ValueError("WebDAV configuration required for provider='webdav'")
        config = WebDAVBackupConfig(
            host=webdav.host,
            username=webdav.username,
            password=webdav.password,
            path=webdav.path,
        )
        return WebDAVBackupStrategy(config)
    elif provider == "s3":
        if not s3:
            raise ValueError("S3 configuration required for provider='s3'")
        config = S3BackupConfig(
            endpoint=s3.endpoint,
            region=s3.region,
            bucket=s3.bucket,
            access_key_id=s3.access_key_id,
            secret_access_key=s3.secret_access_key,
            prefix=s3.prefix,
            force_path_style=s3.force_path_style,
        )
        return S3BackupStrategy(config)
    else:
        raise ValueError(f"Unsupported provider: {provider}")
