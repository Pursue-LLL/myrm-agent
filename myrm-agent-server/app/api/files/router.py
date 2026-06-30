"""Files API router

Main router that aggregates all file-related endpoints.
"""

import logging

from fastapi import APIRouter

from app.api.files import (
    artifact_api,
    artifact_share_api,
    browse,
    document_extract,
    evicted,
    hosting_api,
    local_actions,
    pdf_extract,
    revert,
    storage,
    suggest,
    upload,
    vault_api,
    workspace_ops,
)

logger = logging.getLogger(__name__)

router = APIRouter()

router.include_router(upload.router, tags=["files-upload"])
router.include_router(vault_api.router, prefix="/vault", tags=["files-vault"])
router.include_router(artifact_api.router, prefix="/artifacts", tags=["files-artifacts"])
router.include_router(hosting_api.router, prefix="/artifacts", tags=["files-hosting"])
router.include_router(artifact_share_api.router, prefix="/artifacts", tags=["files-artifact-share"])
router.include_router(storage.router, prefix="/storage", tags=["files-storage"])
router.include_router(pdf_extract.router, tags=["files-pdf"])
router.include_router(document_extract.router, tags=["files-document"])
router.include_router(revert.router, prefix="/revert", tags=["files-revert"])
router.include_router(browse.router, tags=["files-browse"])
router.include_router(evicted.router, tags=["files-evicted"])
router.include_router(suggest.router, tags=["files-suggest"])
router.include_router(local_actions.router, tags=["files-local-actions"])
router.include_router(workspace_ops.router, tags=["files-workspace-ops"])
