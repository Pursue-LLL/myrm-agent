"""SSRF-safe HTTP target resolution for channel media downloads.

[INPUT]
- url: Target URL to fetch
- config: MediaDownloadConfig with SSRF and redirect settings
- http_client: httpx.AsyncClient for redirect resolution
- headers: Request headers to merge with pin headers

[OUTPUT]
- SecureHttpTarget: Pinned request URL and headers for streaming fetch

[POS]
Extracted from MediaDownloader to keep downloader.py under the line budget gate.
"""

from __future__ import annotations

import httpx
from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError, async_pin_url
from myrm_agent_harness.core.security.http.secure_fetch import (
    SecureHttpTarget,
    resolve_secure_http_target,
)

from .config import MediaDownloadConfig
from .exceptions import SSRFError


async def resolve_media_ssrf_target(
    *,
    url: str,
    config: MediaDownloadConfig,
    http_client: httpx.AsyncClient,
    headers: dict[str, str],
) -> SecureHttpTarget:
    """Resolve a media download URL to an SSRF-pinned HTTP target."""
    if not config.validate_ssrf:
        return SecureHttpTarget(
            logical_url=url,
            request_url=url,
            headers=headers,
            method="GET",
        )

    try:
        if config.follow_redirects:
            return await resolve_secure_http_target(
                http_client,
                url,
                headers=headers,
            )
        pinned_url, pin_headers = await async_pin_url(url)
        return SecureHttpTarget(
            logical_url=url,
            request_url=pinned_url,
            headers={**headers, **pin_headers},
            method="GET",
        )
    except SSRFSecurityError as exc:
        raise SSRFError(str(exc), url) from exc
