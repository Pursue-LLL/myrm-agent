"""Shared helpers for pairing deep links and absolute mobile URLs.

[POS]
Keep pairing path/url derivation in one place so router responses and
server-side takeover SSE enrichment stay consistent.
"""

from __future__ import annotations

from app.core.infra.ingress import get_public_ingress_base_url
from app.remote_access.mobile_deep_link import resolve_mobile_remote_base_url
from app.remote_access.pairing import BROWSER_TAKEOVER_PURPOSE


def mobile_path_for_pairing_token(*, token: str, purpose: str, chat_id: str | None) -> str:
    """Build mobile deep-link path for a pairing token."""
    if chat_id and purpose == BROWSER_TAKEOVER_PURPOSE:
        return f"/mobile/takeover/{chat_id}?pair={token}"
    if chat_id:
        return f"/mobile/status/{chat_id}?pair={token}"
    return f"/mobile?pair={token}"


async def mobile_url_for_path(mobile_path: str) -> str | None:
    """Resolve absolute mobile URL for a deep-link path when ingress is known."""
    ingress = await get_public_ingress_base_url()
    base = resolve_mobile_remote_base_url(public_ingress_base_url=ingress)
    if not base:
        return None
    normalized_path = mobile_path if mobile_path.startswith("/") else f"/{mobile_path}"
    return f"{base}{normalized_path}"


__all__ = ["mobile_path_for_pairing_token", "mobile_url_for_path"]
