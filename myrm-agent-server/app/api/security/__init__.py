"""Security API module — dashboard and profile management."""

from .profiles import router as profiles_router
from .tainted_egress import router as tainted_egress_router

__all__ = ["profiles_router", "tainted_egress_router"]
