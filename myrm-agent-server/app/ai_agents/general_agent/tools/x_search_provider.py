"""X/Twitter search provider backed by xAI's Live Search API.

Provides dedicated X/Twitter search capability via xAI's Responses API,
returning structured results with inline citations for precise source attribution.

Authentication: xAI API key is read from session context (issuer=xai) at tool execution time.

[INPUT]
- httpx (POS: async HTTP client)
- myrm_agent_harness.toolkits.web_search.common::SearchResult, Citation (POS: search result types)

[OUTPUT]
- XSearchProvider: xAI Live Search API client
- XSearchProviderConfig, XSearchInput: configuration and tool input schema

[POS]
Server-layer X/Twitter search provider. API client used by integrations/tools/x_live_search.py.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx
from myrm_agent_harness.toolkits.web_search.common import Citation, SearchResult
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
_DEFAULT_MODEL = "grok-3"
_DEFAULT_TIMEOUT_SECONDS = 60
_MAX_HANDLES = 10
_MAX_RETRIES = 2


class XSearchProviderConfig(BaseModel):
    """Configuration for xAI X Search provider."""

    api_key: str = Field(default="", description="xAI API key")
    base_url: str = Field(default=_DEFAULT_XAI_BASE_URL, description="xAI API base URL")
    model: str = Field(default=_DEFAULT_MODEL, description="Model for xAI Responses API")
    timeout_seconds: int = Field(default=_DEFAULT_TIMEOUT_SECONDS, ge=10, le=300)


def _resolve_xai_credentials(config: XSearchProviderConfig) -> XSearchProviderConfig:
    """Use explicit config only (credentials come from WebUI providers)."""
    return config.model_copy(update={"base_url": config.base_url.rstrip("/") or _DEFAULT_XAI_BASE_URL})


def _normalize_handles(handles: list[str] | None) -> list[str]:
    """Normalize and validate X handles."""
    cleaned: list[str] = []
    for handle in handles or []:
        normalized = str(handle or "").strip().lstrip("@")
        if normalized:
            cleaned.append(normalized)
    if len(cleaned) > _MAX_HANDLES:
        raise ValueError(f"Maximum {_MAX_HANDLES} handles allowed")
    return cleaned


def _validate_date_range(from_date: str, to_date: str) -> str | None:
    """Validate from_date / to_date before they reach xAI.

    Returns an error message if validation fails, None if valid.
    xAI silently returns a billable 200 with fabricated content for malformed
    dates, so client-side validation prevents wasted API calls and misleading results.
    """
    parsed_from: date | None = None
    parsed_to: date | None = None
    for raw, label in ((from_date, "from_date"), (to_date, "to_date")):
        trimmed = raw.strip()
        if not trimmed:
            continue
        try:
            parsed = datetime.strptime(trimmed, "%Y-%m-%d").date()
        except ValueError:
            return f"{label} must be YYYY-MM-DD (got {trimmed!r})"
        if label == "from_date":
            parsed_from = parsed
        else:
            parsed_to = parsed
    if parsed_from and parsed_to and parsed_from > parsed_to:
        return f"from_date ({parsed_from.isoformat()}) must be on or before to_date ({parsed_to.isoformat()})"
    if parsed_from is not None and parsed_from > datetime.now(timezone.utc).date():
        return f"from_date ({parsed_from.isoformat()}) is in the future; X Search only indexes past posts"
    return None


class XSearchProvider:
    """xAI Live Search API provider for X/Twitter content.

    Uses xAI's Responses API with built-in x_search tool type for
    precise X/Twitter content retrieval with inline citations.
    """

    def __init__(self, config: XSearchProviderConfig) -> None:
        self._config = _resolve_xai_credentials(config)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._config.timeout_seconds)
        return self._client

    def is_available(self) -> bool:
        """Check if xAI credentials are configured."""
        return bool(self._config.api_key)

    async def search(
        self,
        query: str,
        *,
        allowed_handles: list[str] | None = None,
        excluded_handles: list[str] | None = None,
        from_date: str = "",
        to_date: str = "",
        enable_image_understanding: bool = False,
        enable_video_understanding: bool = False,
    ) -> SearchResult:
        """Execute X/Twitter search via xAI Responses API.

        Args:
            query: Search query
            allowed_handles: X handles to include exclusively (max 10)
            excluded_handles: X handles to exclude (max 10)
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format
            enable_image_understanding: Analyze images in matching posts
            enable_video_understanding: Analyze videos in matching posts

        Returns:
            SearchResult with inline citations
        """
        if not self.is_available():
            return SearchResult(
                title="X Search Error",
                link="",
                snippet="xAI API key not configured. Add an xAI provider in WebUI Settings.",
                is_error=True,
            )

        try:
            allowed = _normalize_handles(allowed_handles)
            excluded = _normalize_handles(excluded_handles)
            if allowed and excluded:
                return SearchResult(
                    title="X Search Error",
                    link="",
                    snippet="allowed_handles and excluded_handles cannot be used together",
                    is_error=True,
                )

            date_error = _validate_date_range(from_date, to_date)
            if date_error:
                return SearchResult(
                    title="X Search Error",
                    link="",
                    snippet=date_error,
                    is_error=True,
                )

            tool_def: dict[str, Any] = {"type": "x_search"}
            if allowed:
                tool_def["allowed_x_handles"] = allowed
            if excluded:
                tool_def["excluded_x_handles"] = excluded
            if from_date.strip():
                tool_def["from_date"] = from_date.strip()
            if to_date.strip():
                tool_def["to_date"] = to_date.strip()
            if enable_image_understanding:
                tool_def["enable_image_understanding"] = True
            if enable_video_understanding:
                tool_def["enable_video_understanding"] = True

            payload = {
                "model": self._config.model,
                "input": [{"role": "user", "content": query.strip()}],
                "tools": [tool_def],
                "store": False,
            }

            client = await self._get_client()
            headers = {
                "Authorization": f"Bearer {self._config.api_key}",
                "Content-Type": "application/json",
            }
            url = f"{self._config.base_url}/responses"

            response: httpx.Response | None = None
            for attempt in range(_MAX_RETRIES + 1):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    break
                except httpx.HTTPStatusError as e:
                    if e.response.status_code < 500 or attempt >= _MAX_RETRIES:
                        raise
                    logger.warning(
                        "x_search upstream %s on attempt %s/%s",
                        e.response.status_code,
                        attempt + 1,
                        _MAX_RETRIES + 1,
                    )
                    await asyncio.sleep(min(5.0, 1.5 * (attempt + 1)))
                except httpx.TimeoutException:
                    if attempt >= _MAX_RETRIES:
                        raise
                    logger.warning(
                        "x_search timeout on attempt %s/%s",
                        attempt + 1,
                        _MAX_RETRIES + 1,
                    )
                    await asyncio.sleep(min(5.0, 1.5 * (attempt + 1)))

            if response is None:
                return SearchResult(
                    title="X Search Error",
                    link="",
                    snippet="xAI API did not return a response after retries",
                    is_error=True,
                )
            data = response.json()

            answer = self._extract_response_text(data)
            inline_citations = self._extract_inline_citations(data)
            top_level_citations: list[dict[str, Any]] = list(data.get("citations") or [])

            seen_urls: set[str] = set()
            merged: list[Citation] = []
            for c in inline_citations:
                url = c.get("url", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(Citation(
                    url=url,
                    title=c.get("title", ""),
                    start_index=c.get("start_index"),
                    end_index=c.get("end_index"),
                ))
            for tc in top_level_citations:
                url = tc.get("url", "") if isinstance(tc, dict) else str(tc)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(Citation(
                    url=url,
                    title=tc.get("title", "") if isinstance(tc, dict) else "",
                ))

            has_filters = bool(allowed or excluded or from_date.strip() or to_date.strip())
            is_degraded = has_filters and not merged
            if is_degraded:
                answer += (
                    "\n\nNote: No matching posts found for the specified filters. "
                    "This answer may be based on general knowledge rather than actual X posts."
                )

            return SearchResult(
                title=f"X Search: {query[:50]}",
                link=f"https://x.com/search?q={query}",
                snippet=answer,
                citations=merged,
                is_degraded=is_degraded,
            )

        except httpx.HTTPStatusError as e:
            logger.error("x_search HTTP error: %s", e, exc_info=True)
            return SearchResult(
                title="X Search Error",
                link="",
                snippet=f"xAI API error: {e.response.status_code} {e.response.text[:200]}",
                is_error=True,
            )
        except Exception as e:
            logger.error("x_search failed: %s", e, exc_info=True)
            return SearchResult(
                title="X Search Error",
                link="",
                snippet=f"X search failed: {type(e).__name__}: {e}",
                is_error=True,
            )

    @staticmethod
    def _extract_response_text(payload: dict[str, Any]) -> str:
        """Extract response text from xAI Responses API output."""
        output_text = str(payload.get("output_text") or "").strip()
        if output_text:
            return output_text

        parts: list[str] = []
        for item in payload.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                ctype = content.get("type")
                if ctype in ("output_text", "text"):
                    text = str(content.get("text") or "").strip()
                    if text:
                        parts.append(text)
        return "\n\n".join(parts).strip()

    @staticmethod
    def _extract_inline_citations(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract inline citations from xAI Responses API output annotations."""
        citations: list[dict[str, Any]] = []
        for item in payload.get("output", []) or []:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                for annotation in content.get("annotations", []) or []:
                    if annotation.get("type") != "url_citation":
                        continue
                    citations.append(
                        {
                            "url": annotation.get("url", ""),
                            "title": annotation.get("title", ""),
                            "start_index": annotation.get("start_index"),
                            "end_index": annotation.get("end_index"),
                        }
                    )
        return citations


_X_SEARCH_DESCRIPTION = """Search X (Twitter) posts, profiles, and threads using xAI's Live Search API.
Use this for current discussions, reactions, claims, or trending topics on X rather than general web pages.
Returns tweet content with inline citations for precise source attribution.

Requires an xAI provider configured in WebUI Settings.
"""


class XSearchInput(BaseModel):
    """Input schema for X search tool."""

    query: str = Field(description="What to look up on X")
    allowed_handles: list[str] | None = Field(
        default=None,
        description="Optional list of X handles to include exclusively (max 10)",
    )
    excluded_handles: list[str] | None = Field(
        default=None,
        description="Optional list of X handles to exclude (max 10)",
    )
    from_date: str = Field(
        default="",
        description="Optional start date in YYYY-MM-DD format",
    )
    to_date: str = Field(
        default="",
        description="Optional end date in YYYY-MM-DD format",
    )
