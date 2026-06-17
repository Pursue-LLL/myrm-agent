"""Build scoped mobile status URLs for channel HITL notifications.

[INPUT]
- app.remote_access.pairing::create_pairing_token (POS: Signed short-lived mobile deep link tokens)
- app.remote_access.tunnel_manager::get_tunnel_manager (POS: CF quick tunnel lifecycle for G1-global remote access)
- app.core.infra.ingress::get_public_ingress_base_url (POS: Public Ingress URL resolver)

[OUTPUT]
- resolve_mobile_remote_base_url: Prefer tunnel public URL, else configured ingress base
- build_mobile_status_deep_link: Scoped `/mobile/status/{chatId}?pair=` URL
- resolve_mobile_status_deep_link: Async helper for channel outbound buttons

[POS]
Channel-to-mobile bridge. Builds scoped pairing deep links when a public base URL exists;
no I/O beyond tunnel status and ingress lookup.
"""

from __future__ import annotations

from app.remote_access.pairing import create_pairing_token
from app.remote_access.tunnel_manager import TunnelState, get_tunnel_manager


def resolve_mobile_remote_base_url(*, public_ingress_base_url: str = "") -> str:
    """Prefer running CF quick tunnel URL, then configured public ingress."""
    tunnel = get_tunnel_manager().status()
    if tunnel.state == TunnelState.RUNNING and tunnel.public_url:
        return tunnel.public_url.rstrip("/")
    if public_ingress_base_url:
        return public_ingress_base_url.rstrip("/")
    return ""


def build_mobile_status_deep_link(*, chat_id: str, base_url: str) -> str | None:
    """Build scoped mobile status URL when a public base URL is available."""
    if not base_url or not chat_id:
        return None
    token = create_pairing_token(chat_id=chat_id, purpose="mobile_hub")
    return f"{base_url}/mobile/status/{chat_id}?pair={token}"


async def resolve_mobile_status_deep_link(chat_id: str) -> str | None:
    from app.core.infra.ingress import get_public_ingress_base_url

    ingress = await get_public_ingress_base_url()
    base = resolve_mobile_remote_base_url(public_ingress_base_url=ingress)
    return build_mobile_status_deep_link(chat_id=chat_id, base_url=base)


__all__ = [
    "build_mobile_status_deep_link",
    "resolve_mobile_remote_base_url",
    "resolve_mobile_status_deep_link",
]
