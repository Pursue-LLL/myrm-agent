"""Memory API router

Main router that aggregates all memory-related endpoints.
"""

import logging

from fastapi import APIRouter

from app.api.memory.follow_ups import router as follow_ups_router
from app.api.memory.operations import (
    archival,
    backup,
    backup_remote,
    command_center,
    crud,
    guardian,
    pending,
    reindex,
    shared_context_health,
    shared_context_history,
    shared_context_migration,
    shared_contexts,
    working_state,
)

logger = logging.getLogger(__name__)

router = APIRouter()

router.include_router(command_center.router, tags=["memory-command-center"])
router.include_router(pending.router, tags=["memory-pending"])
router.include_router(shared_context_health.router, tags=["memory-shared-contexts"])
router.include_router(shared_contexts.router, tags=["memory-shared-contexts"])
router.include_router(shared_context_history.router, tags=["memory-shared-contexts"])
router.include_router(shared_context_migration.router, tags=["memory-shared-contexts"])
router.include_router(guardian.router, tags=["memory-guardian"])
router.include_router(working_state.router, tags=["memory-working-state"])
router.include_router(crud.router, tags=["memory-crud"])
router.include_router(backup.router, tags=["memory-backup"])
router.include_router(backup_remote.router, tags=["memory-backup-remote"])
router.include_router(archival.router, tags=["memory-archival"])
router.include_router(reindex.router, tags=["memory-reindex"])
router.include_router(follow_ups_router, tags=["memory-follow-ups"])
