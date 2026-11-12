"""Security sub-router registration assembly.

Aggregates all modular security domain routers and registers them to the root security router.
Maintains clean architectural boundaries and prevents single-file length inflation.

[INPUT]
- app.api.security.inbound_quarantine_router::router (POS: REST API layer providing physical credential quarantine and direct human release endpoints.)

[OUTPUT]
- register_security_subrouters: includes every modular security sub-router on the parent security router

[POS]
Registration point of the security API: the one place that lists the modular security sub-routers and mounts them on the
parent security router.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.security.inbound_quarantine_router import router as inbound_quarantine_router

_SECURITY_SUBROUTERS: tuple[APIRouter, ...] = (inbound_quarantine_router,)


def register_security_subrouters(parent_router: APIRouter) -> None:
    """Register all modular security sub-routers onto the parent security router."""
    for sub in _SECURITY_SUBROUTERS:
        parent_router.include_router(sub)
