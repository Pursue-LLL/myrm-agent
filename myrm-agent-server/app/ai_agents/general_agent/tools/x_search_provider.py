"""X/Twitter search provider backed by xAI's Live Search API.

Provides dedicated X/Twitter search capability via xAI's Responses API,
returning structured results with inline citations for precise source attribution.

Authentication supports:
- Explicit config.api_key from WebUI providers
- OAuth access token (from frontend config)

[INPUT]
- httpx (POS: async HTTP client)
- myrm_agent_harness.toolkits.web_search.common::SearchResult, Citation (POS: search result types)

[OUTPUT]
- XSearchProvider: xAI Live Search implementation
- create_x_search_tool: factory function for LangChain tool registration

[POS]
Server-layer X/Twitter search provider. Implements xAI Responses API integration
as an optional skill, not a built-in tool. Follows harness SearchResult contract.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain.tools import tool
from myrm_agent_harness.toolkits.web_search.common import Citation, SearchResult
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_DEFAULT_XAI_BASE_URL = "https://api.x.ai/v1"
_DEFAULT_MODEL = "grok-3"
_DEFAULT_TIMEOUT_SECONDS = 60
_MAX_HANDLES = 10


class XSearchProviderConfig(BaseModel):
    """Configuration for xAI X Search provider."""

    api_key: str = Field(default="", description="xAI API key")
    base_url: str = Field(default=_DEFAULT_XAI_BASE_URL, description="xAI API base URL")
    model: str = Field(default=_DEFAULT_MODEL, description="Model for xAI Responses API")
    timeout_seconds: int = Field(default=_DEFAULT_TIMEOUT_SECONDS, ge=10, le=300)


def _resolve_xai_credentials(config: XSearchProviderConfig) -> XSearchProviderConfig:
    """Use explicit config only (credentials come from WebUI providers)."""
    return config.model_copy(
        update={"base_url": config.base_url.rstrip("/") or _DEFAULT_XAI_BASE_URL}
    )


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
            response = await client.post(
                f"{self._config.base_url}/responses",
                headers={
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            answer = self._extract_response_text(data)
            inline_citations = self._extract_inline_citations(data)

            return SearchResult(
                title=f"X Search: {query[:50]}",
                link=f"https://x.com/search?q={query}",
                snippet=answer,
                citations=[
                    Citation(
                        url=c.get("url", ""),
                        title=c.get("title", ""),
                        start_index=c.get("start_index"),
                        end_index=c.get("end_index"),
                    )
                    for c in inline_citations
                    if c.get("url")
                ],
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
                    citations.append({
                        "url": annotation.get("url", ""),
                        "title": annotation.get("title", ""),
                        "start_index": annotation.get("start_index"),
                        "end_index": annotation.get("end_index"),
                    })
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


def create_x_search_tool(config: XSearchProviderConfig | None = None):
    """Create an X/Twitter search tool backed by xAI Live Search API.

    Args:
        config: Optional provider configuration from WebUI Settings. If None, uses empty defaults.

    Returns:
        LangChain tool function for X/Twitter search
    """
    provider = XSearchProvider(config or XSearchProviderConfig())

    @tool("x_search_tool", description=_X_SEARCH_DESCRIPTION, args_schema=XSearchInput)
    async def x_search_func(
        query: str,
        allowed_handles: list[str] | None = None,
        excluded_handles: list[str] | None = None,
        from_date: str = "",
        to_date: str = "",
    ) -> dict[str, Any]:
        """Search X/Twitter content via xAI Live Search API."""
        result = await provider.search(
            query=query,
            allowed_handles=allowed_handles,
            excluded_handles=excluded_handles,
            from_date=from_date,
            to_date=to_date,
        )

        if result.is_error:
            return {
                "content": result.snippet,
                "metadata": {"error": True, "query": query},
            }

        # Format citations for display
        citations_text = ""
        if result.citations:
            citations_text = "\n\nSources:\n" + "\n".join(
                f"- [{c.title or c.url}]({c.url})"
                for c in result.citations
            )

        return {
            "content": result.snippet + citations_text,
            "metadata": {
                "query": query,
                "source": "x_search",
                "citations": [
                    {"url": c.url, "title": c.title}
                    for c in result.citations
                ],
                "total_citations": len(result.citations),
            },
        }

    return x_search_func
