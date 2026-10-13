"""Security sub-router registration assembly.

Aggregates all modular security domain routers and registers them to the root security router.
Maintains clean architectural boundaries and prevents single-file length inflation.

[POS] app/api/security/sub_routers.py
[INPUT] app.api.security.*
[OUTPUT] register_security_subrouters
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.security.inbound_quarantine_router import router as inbound_quarantine_router
from app.api.security.workspace_scoper_router import router as workspace_scoper_router

_SECURITY_SUBROUTERS: tuple[APIRouter, ...] = (
    workspace_scoper_router,
    inbound_quarantine_router,
)


def register_security_subrouters(parent_router: APIRouter) -> None:
    """Register all modular security sub-routers onto the parent security router."""
    for sub in _SECURITY_SUBROUTERS:
        parent_router.include_router(sub)
