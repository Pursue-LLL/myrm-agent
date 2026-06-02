"""Message filter API endpoints."""

from fastapi import APIRouter

from . import audit, config, rules, templates, version

router = APIRouter(prefix="/message-filter", tags=["message-filter"])

router.include_router(config.router, prefix="/config")
router.include_router(rules.router, prefix="/rules")
router.include_router(audit.router, prefix="/audit")
router.include_router(version.router, prefix="/version")
router.include_router(templates.router, prefix="/templates")

__all__ = ["router"]
