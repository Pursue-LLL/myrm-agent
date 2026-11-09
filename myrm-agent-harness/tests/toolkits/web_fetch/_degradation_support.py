"""Shared builders for the FetchEngine tier-degradation test modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import (
    FetcherType,
    FetchResult,
)
from myrm_agent_harness.toolkits.web_fetch.router import TierBreaker


def http_result(html: str, status: int = 200) -> FetchResult:
    return FetchResult(html=html, url="http://example.com/page", status_code=status)


def mock_pipeline() -> MagicMock:
    """Pipeline double whose ``aprocess`` is awaitable, like the real conversion entry point."""
    pipeline = MagicMock()
    pipeline.aprocess = AsyncMock()
    return pipeline


def start_on(engine: FetchEngine, tier: FetcherType) -> MagicMock:
    """Pin the tier crawls start on, whatever the breaker would pick; the returned mock records its reports."""
    breaker = MagicMock(spec=TierBreaker)
    breaker.select.return_value = tier
    engine._tier_breaker = breaker  # type: ignore[assignment]
    return breaker


def stub_fetchers(engine: FetchEngine) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    http = AsyncMock()
    browser = AsyncMock()
    stealth = AsyncMock()
    browser.set_launch_mode_preference = MagicMock()
    stealth.set_launch_mode_preference = MagicMock()
    engine._http_fetcher = http  # type: ignore[assignment]
    engine._browser_fetcher = browser  # type: ignore[assignment]
    engine._stealth_fetcher = stealth  # type: ignore[assignment]
    engine._pipeline = mock_pipeline()  # type: ignore[assignment]
    start_on(engine, FetcherType.HTTP)
    return http, browser, stealth


def make_document(text: str = "content") -> Document:
    return Document(page_content=text, metadata={"title": "page"})


RICH_HTML = "<html><body><article><p>" + ("lorem ipsum content " * 40) + "</p></article></body></html>"
