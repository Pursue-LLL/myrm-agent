"""Security API module — dashboard and profile management."""

from .profiles import router as profiles_router

__all__ = ["profiles_router"]
