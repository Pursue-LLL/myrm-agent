"""Jina Reader remote fetch provider.

[INPUT]
- myrm_agent_harness.toolkits.web_fetch.escalation.protocols::EscalationFetchResult (POS: Fetch result type)
- myrm_agent_harness.core.security.guards.ssrf::async_validate_url_for_ssrf (POS: SSRF guard)

[OUTPUT]
- JinaEscalationProvider: Fetch via Jina Reader (free tier when api_key is None).

[POS]
Jina Reader remote fetch provider implementing FetchEscalationProvider protocol.
"""

from __future__ import annotations

import logging

import httpx
from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf
from myrm_agent_harness.toolkits.web_fetch.escalation.protocols import EscalationFetchResult

logger = logging.getLogger(__name__)

_JINA_BASE = "https://r.jina.ai"
_DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


class JinaEscalationProvider:
    """Fetch via Jina Reader (free tier when api_key is None)."""

    provider_id = "jina"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = (api_key or "").strip() or None

    async def fetch_url(self, url: str, *, max_chars: int = 0) -> EscalationFetchResult | None:
        ssrf = await async_validate_url_for_ssrf(url)
        if not ssrf.safe:
            logger.warning("Jina escalation blocked (SSRF): %s — %s", url, ssrf.error)
            return None

        headers: dict[str, str] = {"Accept": "text/markdown"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(f"{_JINA_BASE}/{url}", headers=headers)
                response.raise_for_status()
                content = response.text.strip()
        except httpx.HTTPError as exc:
            logger.warning("Jina escalation HTTP error for %s: %s", url, exc)
            return None

        if not content:
            return None

        title = ""
        if content.startswith("# "):
            first_line, _, rest = content.partition("\n")
            title = first_line.removeprefix("# ").strip()
            content = rest.strip()

        if max_chars > 0 and len(content) > max_chars:
            content = content[:max_chars]

        return EscalationFetchResult(
            url=url,
            content=content,
            title=title,
            provider_id=self.provider_id,
            is_markdown=True,
        )
