"""Mem0-compatible API router.

[INPUT]
- app.api.mem0_compat.endpoints (POS: Mem0 endpoint implementations)

[OUTPUT]
- mem0_compat_router: Combined router mounted at /mem0

[POS]
Aggregates Mem0-compatible endpoints under /mem0 prefix.
Mem0 SDK users set `host="http://our-server/mem0"` for seamless migration.
"""

from fastapi import APIRouter

from app.api.mem0_compat.endpoints import router as endpoints_router

mem0_compat_router = APIRouter(prefix="/mem0", tags=["mem0-compat"])

mem0_compat_router.include_router(endpoints_router)
