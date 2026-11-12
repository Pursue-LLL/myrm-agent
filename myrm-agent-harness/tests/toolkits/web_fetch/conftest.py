"""Shared fixtures for web_fetch tests."""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from types import ModuleType
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.web_fetch.probe.http3_probe import reset_http3_state_for_tests


@pytest.fixture
def install_fake_scrapling() -> Iterator[AsyncMock]:
    """Install a minimal scrapling.fetchers module for HttpFetcher tests.

    The yielded mock stands in for the request: it receives the request parameters and returns the response. The body
    of that response reaches the fetcher the way libcurl delivers it, through the write callback.
    """
    mock_get = AsyncMock()

    async def get(url: str, *, content_callback: Callable[[bytes], int] | None = None, **kwargs: object) -> object:
        response = await mock_get(url, **kwargs)
        if content_callback is not None and isinstance(response.body, bytes):
            content_callback(response.body)
        return response

    fetchers_mod = ModuleType("scrapling.fetchers")
    fetchers_mod.AsyncFetcher = type("AsyncFetcher", (), {"get": staticmethod(get)})

    scrapling_mod = ModuleType("scrapling")
    scrapling_mod.fetchers = fetchers_mod

    sys.modules["scrapling"] = scrapling_mod
    sys.modules["scrapling.fetchers"] = fetchers_mod
    try:
        yield mock_get
    finally:
        sys.modules.pop("scrapling.fetchers", None)
        sys.modules.pop("scrapling", None)


@pytest.fixture
def http3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """L1 HTTP/3 retry on, SSRF shield off, probe state and retry counters reset."""
    reset_http3_state_for_tests()
    monkeypatch.setenv("MYRM_HTTP3_RETRY", "1")
    monkeypatch.setenv("MYRM_ENABLE_SSRF_SHIELD", "false")
