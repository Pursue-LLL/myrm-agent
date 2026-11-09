"""Shared builders for the FetchEngine tier-degradation test modules."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from langchain_core.documents import Document

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import (
    FetcherType,
    FetchResult,
)


def make_engine(tmpdir: str) -> FetchEngine:
    return FetchEngine(adaptive_router_rules_file=Path(tmpdir) / "rules.pkl")


def http_result(html: str, status: int = 200) -> FetchResult:
    return FetchResult(html=html, url="http://example.com/page", status_code=status)


def mock_pipeline() -> MagicMock:
    """Pipeline double whose ``aprocess`` is awaitable, like the real conversion entry point."""
    pipeline = MagicMock()
    pipeline.aprocess = AsyncMock()
    return pipeline


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
    engine._router = SimpleNamespace(
        select=lambda url: SimpleNamespace(fetcher_type=FetcherType.HTTP),
        report_result=lambda *a, **k: None,
        shutdown=lambda: None,
    )
    return http, browser, stealth


def make_document(text: str = "content") -> Document:
    return Document(page_content=text, metadata={"title": "page"})


RICH_HTML = "<html><body><article><p>" + ("lorem ipsum content " * 40) + "</p></article></body></html>"
