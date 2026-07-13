"""Proxy control-plane rate-limit status for sandbox security UI."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.schemas.security.dashboard import RateLimitStatusItem, SecurityRateLimitsResponse
from app.config.deploy_mode import is_sandbox
from app.services.security.cp_security_dashboard import get_cp_api_base, get_cp_request_headers

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 8.0


async def fetch_cp_rate_limits() -> SecurityRateLimitsResponse:
    if not is_sandbox():
        return SecurityRateLimitsResponse(items=[], is_live=False)

    base = get_cp_api_base()
    headers = get_cp_request_headers()
    if not base or not headers:
        return SecurityRateLimitsResponse(items=[], is_live=False)

    url = f"{base}/api/internal/security/rate-limits"
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            if response.status_code in (403, 404, 503):
                return SecurityRateLimitsResponse(items=[], is_live=False)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("Control plane rate limits unavailable: %s", exc)
        return SecurityRateLimitsResponse(items=[], is_live=False)

    if not isinstance(data, dict):
        return SecurityRateLimitsResponse(items=[], is_live=False)

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        return SecurityRateLimitsResponse(items=[], is_live=False)

    items: list[RateLimitStatusItem] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        items.append(_map_rate_item(entry))

    return SecurityRateLimitsResponse(items=items, is_live=True)


def _map_rate_item(entry: dict[str, Any]) -> RateLimitStatusItem:
    current = int(entry.get("current") or 0)
    max_val = int(entry.get("max") or 0)
    remaining = int(entry.get("remaining") or max(0, max_val - current))
    return RateLimitStatusItem(
        user_id=str(entry.get("user_id") or ""),
        resource=str(entry.get("resource") or ""),
        current=current,
        max=max_val,
        remaining=remaining,
        window_seconds=int(entry.get("window_seconds") or 0),
    )
