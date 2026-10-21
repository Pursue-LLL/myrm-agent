"""Security API module — dashboard and profile management.

[INPUT]
- None.

[OUTPUT]
- Lazy exports of security routers avoiding heavy eager dependency chains.

[POS]
- Package initialization for app.api.security.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

__all__ = ["profiles_router"]


def __getattr__(name: str) -> APIRouter:
    if name == "profiles_router":
        from .profiles import router as profiles_router_inst

        return profiles_router_inst
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
