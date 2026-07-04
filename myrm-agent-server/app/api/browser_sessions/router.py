"""Browser Sessions API — manage saved browser login sessions.

[INPUT]
- app.core.security.browser_vault::get_global_session_vault (POS: global SessionVault singleton)

[OUTPUT]
- router: FastAPI APIRouter with session management endpoints

[POS]
REST entry layer for browser session vault management.
Exposes list/delete/cleanup operations on encrypted browser sessions.
Never returns raw storage_state (cookies/localStorage) — only metadata summaries.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


class SessionSummaryResponse(BaseModel):
    domain: str
    created_at: str
    expires_at: str | None
    is_expired: bool
    cookie_count: int
    local_storage_count: int


class CleanupResponse(BaseModel):
    removed: int


def _ts_to_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


@router.get("/sessions")
async def list_sessions() -> list[SessionSummaryResponse]:
    """List all saved browser sessions (metadata only, no sensitive data)."""
    from app.core.security.browser_vault import get_global_session_vault

    vault = get_global_session_vault()
    summaries = await vault.list_summaries()
    return [
        SessionSummaryResponse(
            domain=s.domain,
            created_at=_ts_to_iso(s.created_at),
            expires_at=_ts_to_iso(s.expires_at) if s.expires_at else None,
            is_expired=s.is_expired,
            cookie_count=s.cookie_count,
            local_storage_count=s.local_storage_count,
        )
        for s in summaries
    ]


@router.delete("/sessions/{domain}")
async def delete_session(domain: str) -> dict[str, bool]:
    """Delete a saved browser session by domain."""
    from app.core.security.browser_vault import get_global_session_vault

    vault = get_global_session_vault()
    existed = await vault.delete(domain)
    if not existed:
        raise HTTPException(status_code=404, detail=f"No saved session for domain: {domain}")
    logger.info("Deleted browser session for domain: %s", domain)
    return {"deleted": True}


@router.post("/sessions/cleanup", response_model=CleanupResponse)
async def cleanup_expired_sessions() -> CleanupResponse:
    """Remove all expired browser sessions."""
    from app.core.security.browser_vault import get_global_session_vault

    vault = get_global_session_vault()
    removed = await vault.cleanup_expired()
    if removed > 0:
        logger.info("Cleaned up %d expired browser sessions", removed)
    return CleanupResponse(removed=removed)
