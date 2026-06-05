"""Context bundle and context search HTTP API."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.context.bundle import (
    ContextBundleHealthResponse,
    ContextBundleMigrationResponse,
)
from app.schemas.context.search import ContextSearchRequest, ContextSearchResponse
from app.services.context.context_bundle_service import ContextBundleService
from app.services.context.context_search_deps import build_context_search_service
from app.services.context.context_search_service import ContextSearchService

router = APIRouter(prefix="/context-bundle", tags=["context-bundle"])


@router.get("", response_model=ContextBundleHealthResponse)
async def get_context_bundle() -> ContextBundleHealthResponse:
    return await ContextBundleService().get_health()


@router.post("/migrate/dry-run", response_model=ContextBundleMigrationResponse)
async def dry_run_context_bundle_migration() -> ContextBundleMigrationResponse:
    return ContextBundleService().run_migration_dry_run()


@router.post("/migrate/apply", response_model=ContextBundleMigrationResponse)
async def apply_context_bundle_migration() -> ContextBundleMigrationResponse:
    return ContextBundleService().apply_migration()


search_router = APIRouter(prefix="/context-search", tags=["context-search"])


@search_router.post("", response_model=ContextSearchResponse)
async def context_search(
    body: ContextSearchRequest,
    service: ContextSearchService = Depends(build_context_search_service),
) -> ContextSearchResponse:
    return await service.search(body.query, top_k=body.top_k)
