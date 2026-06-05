"""Context bundle HTTP API."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.context.bundle import (
    ContextBundleHealthResponse,
    ContextBundleMigrationResponse,
)
from app.services.context.context_bundle_service import ContextBundleService

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
