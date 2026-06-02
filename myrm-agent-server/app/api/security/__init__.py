"""Security API module — dashboard and profile management."""

from .profiles import router as profiles_router
from .router import router

__all__ = ["profiles_router", "router"]
