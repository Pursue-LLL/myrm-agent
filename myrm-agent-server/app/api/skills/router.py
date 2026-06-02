"""Skills API router — aggregates all skill-related endpoints."""

from fastapi import APIRouter

from app.api.skills import (
    batch_import,
    config,
    core,
    curator,
    discovery,
    drafts,
    history,
    instances,
    local,
    packaging,
    permissions,
    prebuilt,
    sync,
)

# Keep backward compatibility for imports from other modules

router = APIRouter()

router.include_router(batch_import.router)
router.include_router(prebuilt.router, tags=["skills-prebuilt"])
router.include_router(local.router, tags=["skills-local"])
router.include_router(discovery.router, tags=["skills-discovery"])
router.include_router(sync.router, tags=["skills-sync"])
router.include_router(drafts.router, tags=["skills-drafts"])

# curator MUST be before routers with /{skill_id} catch-all patterns
router.include_router(curator.router, tags=["skills-curator"])

# These routers have /{skill_id}/... patterns that could match /curator/...
router.include_router(packaging.router, tags=["skills-packaging"])
router.include_router(permissions.router, tags=["skills-permissions"])
router.include_router(history.router, tags=["skills-history"])
router.include_router(instances.router, tags=["skills-instances"])
router.include_router(config.router, tags=["skills-config"])
# core.router MUST be last — it has a catch-all GET /{skill_id} route
router.include_router(core.router, tags=["skills-core"])
