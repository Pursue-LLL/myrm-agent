"""Tests for search topology URL resolution."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.web_search.constants import (
    SEARXNG_DOCKER_SERVICE_URL,
    SEARXNG_HOST_URL,
)

from app.core.channel_bridge.search_topology import (
    get_default_searxng_api_base,
    get_searxng_probe_candidate_urls,
    reset_search_topology_cache_for_testing,
)


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    reset_search_topology_cache_for_testing()
    yield
    reset_search_topology_cache_for_testing()


def test_default_url_on_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "exists", lambda self: False)
    assert get_default_searxng_api_base() == SEARXNG_HOST_URL


def test_default_url_in_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "exists", lambda self: self == Path("/.dockerenv"))
    assert get_default_searxng_api_base() == SEARXNG_DOCKER_SERVICE_URL


def test_probe_candidates_in_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "exists", lambda self: self == Path("/.dockerenv"))
    urls = get_searxng_probe_candidate_urls()
    assert urls[0] == SEARXNG_DOCKER_SERVICE_URL
