"""Resolve sandbox outbound public IP for WeChat Official Account IP whitelist setup.

[INPUT]
- httpx (HTTP client for egress probe)

[OUTPUT]
- resolve_public_egress_ip: Best-effort public IPv4/IPv6 string for the active egress path

[POS]
Business-layer egress probe used by WeChat Official settings UI. Runs from the same
sandbox network path as WeChat API calls so the displayed IP matches whitelist needs.
"""

from __future__ import annotations

import ipaddress
import logging

import httpx

logger = logging.getLogger(__name__)

_PROBE_URL = "https://api.ipify.org?format=json"
_PROBE_TIMEOUT_SECONDS = 8.0


async def resolve_public_egress_ip() -> str:
    """Return the sandbox public egress IP used for outbound HTTPS."""
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.get(_PROBE_URL)
        response.raise_for_status()
        payload = response.json()
    origin = payload.get("ip") if isinstance(payload, dict) else None
    if not isinstance(origin, str) or not origin.strip():
        raise RuntimeError("Egress probe returned no IP address")
    normalized = origin.strip()
    try:
        ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise RuntimeError(f"Egress probe returned invalid IP: {normalized}") from exc
    return normalized
