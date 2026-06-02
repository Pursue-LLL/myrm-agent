"""Local file search API routes.

[INPUT]
- app.services.local_file_search.service (POS: business service)

[OUTPUT]
- router: FastAPI APIRouter for local file search management

[POS]
REST API for managing local file search: directory CRUD, indexing triggers, and status queries.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.local_file_search.service import get_local_file_search_service

logger = logging.getLogger(__name__)

router = APIRouter()


class AddDirectoryRequest(BaseModel):
    path: str = Field(description="Absolute path to directory")
    recursive: bool = Field(default=True, description="Index subdirectories")


class UpdateDirectoryRequest(BaseModel):
    enabled: bool | None = None
    recursive: bool | None = None


class DirectoryResponse(BaseModel):
    id: str
    path: str
    recursive: bool
    enabled: bool
    created_at: str


class IndexStatsResponse(BaseModel):
    total_files: int = 0
    total_chunks: int = 0
    total_directories: int = 0
    status: str = "idle"
    last_indexed_at: str | None = None
    indexing_progress: float = 0.0
    current_file: str | None = None
    error_count: int = 0


class ConfigResponse(BaseModel):
    directories: list[DirectoryResponse] = Field(default_factory=list)
    stats: IndexStatsResponse = Field(default_factory=IndexStatsResponse)


@router.get("", response_model=ConfigResponse)
async def get_config() -> ConfigResponse:
    """Get local file search configuration and status."""
    svc = get_local_file_search_service()
    if not svc.is_initialized:
        await svc.initialize()

    dirs = [
        DirectoryResponse(
            id=d.id,
            path=d.path,
            recursive=d.recursive,
            enabled=d.enabled,
            created_at=d.created_at.isoformat(),
        )
        for d in svc.config.directories
    ]

    stats = svc.get_stats()

    return ConfigResponse(
        directories=dirs,
        stats=IndexStatsResponse(
            total_files=stats.total_files,
            total_chunks=stats.total_chunks,
            total_directories=stats.total_directories,
            status=stats.status.value,
            last_indexed_at=stats.last_indexed_at.isoformat() if stats.last_indexed_at else None,
            indexing_progress=stats.indexing_progress,
            current_file=stats.current_file,
            error_count=stats.error_count,
        ),
    )


@router.post("/directories", response_model=DirectoryResponse, status_code=201)
async def add_directory(request: AddDirectoryRequest) -> DirectoryResponse:
    """Add a directory for indexing."""
    svc = get_local_file_search_service()
    if not svc.is_initialized:
        await svc.initialize()

    try:
        d = await svc.add_directory(request.path, request.recursive)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return DirectoryResponse(
        id=d.id,
        path=d.path,
        recursive=d.recursive,
        enabled=d.enabled,
        created_at=d.created_at.isoformat(),
    )


@router.patch("/directories/{directory_id}", response_model=DirectoryResponse)
async def update_directory(directory_id: str, request: UpdateDirectoryRequest) -> DirectoryResponse:
    """Update directory settings."""
    svc = get_local_file_search_service()
    d = await svc.update_directory(directory_id, enabled=request.enabled, recursive=request.recursive)
    if d is None:
        raise HTTPException(status_code=404, detail="Directory not found")

    return DirectoryResponse(
        id=d.id,
        path=d.path,
        recursive=d.recursive,
        enabled=d.enabled,
        created_at=d.created_at.isoformat(),
    )


@router.delete("/directories/{directory_id}", status_code=204)
async def remove_directory(directory_id: str) -> None:
    """Remove a directory and its indexed data."""
    svc = get_local_file_search_service()
    removed = await svc.remove_directory(directory_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Directory not found")


@router.post("/index", response_model=IndexStatsResponse)
async def trigger_index() -> IndexStatsResponse:
    """Trigger an indexing run. Non-blocking — returns current status immediately."""
    svc = get_local_file_search_service()
    if not svc.is_initialized:
        await svc.initialize()

    try:
        stats = await svc.trigger_index()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return IndexStatsResponse(
        total_files=stats.total_files,
        total_chunks=stats.total_chunks,
        total_directories=stats.total_directories,
        status=stats.status.value,
        last_indexed_at=stats.last_indexed_at.isoformat() if stats.last_indexed_at else None,
        indexing_progress=stats.indexing_progress,
        current_file=stats.current_file,
        error_count=stats.error_count,
    )


@router.get("/stats", response_model=IndexStatsResponse)
async def get_stats() -> IndexStatsResponse:
    """Get current indexing statistics."""
    svc = get_local_file_search_service()
    stats = svc.get_stats()
    return IndexStatsResponse(
        total_files=stats.total_files,
        total_chunks=stats.total_chunks,
        total_directories=stats.total_directories,
        status=stats.status.value,
        last_indexed_at=stats.last_indexed_at.isoformat() if stats.last_indexed_at else None,
        indexing_progress=stats.indexing_progress,
        current_file=stats.current_file,
        error_count=stats.error_count,
    )
