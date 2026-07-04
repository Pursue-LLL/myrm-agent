"""Firecrawl scrape remote fetch provider.

[INPUT]
- myrm_agent_harness.toolkits.web_fetch.escalation.protocols::EscalationFetchResult (POS: Fetch result type)
- myrm_agent_harness.core.security.guards.ssrf::async_validate_url_for_ssrf (POS: SSRF guard)

[OUTPUT]
- FirecrawlEscalationProvider: Fetch via Firecrawl scrape API (requires API key).

[POS]
Firecrawl scrape remote fetch provider implementing FetchEscalationProvider protocol.
"""

from __future__ import annotations

import logging

import httpx
from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf
from myrm_agent_harness.toolkits.web_fetch.escalation.protocols import EscalationFetchResult

logger = logging.getLogger(__name__)

_FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v1/scrape"
_DEFAULT_TIMEOUT = httpx.Timeout(90.0, connect=15.0)


class FirecrawlEscalationProvider:
    """Fetch via Firecrawl scrape API (requires API key)."""

    provider_id = "firecrawl"

    def __init__(self, api_key: str) -> None:
        key = api_key.strip()
        if not key:
            raise ValueError("Firecrawl API key is required")
        self._api_key = key

    async def fetch_url(self, url: str, *, max_chars: int = 0) -> EscalationFetchResult | None:
        ssrf = await async_validate_url_for_ssrf(url)
        if not ssrf.safe:
            logger.warning("Firecrawl escalation blocked (SSRF): %s — %s", url, ssrf.error)
            return None

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"url": url, "formats": ["markdown"]}

        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                response = await client.post(_FIRECRAWL_SCRAPE_URL, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            logger.warning("Firecrawl escalation HTTP error for %s: %s", url, exc)
            return None
        except ValueError as exc:
            logger.warning("Firecrawl escalation invalid JSON for %s: %s", url, exc)
            return None

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            return None

        content = str(data.get("markdown") or data.get("content") or "").strip()
        if not content:
            return None

        metadata = data.get("metadata")
        title = ""
        if isinstance(metadata, dict):
            title = str(metadata.get("title") or "")

        if max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars]

        return EscalationFetchResult(
            url=str(data.get("url") or url),
            content=content,
            title=title,
            provider_id=self.provider_id,
            is_markdown=True,
        )
