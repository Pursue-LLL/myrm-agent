"""Resolve SearXNG api_base from deployment topology."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from myrm_agent_harness.toolkits.web_search.constants import (
    SEARXNG_DOCKER_SERVICE_URL,
    SEARXNG_HOST_URL,
    SEARXNG_PROBE_CANDIDATE_URLS,
)


def is_running_inside_docker() -> bool:
    """Return True when the server process runs inside a container."""
    return Path("/.dockerenv").exists()


@lru_cache(maxsize=1)
def get_default_searxng_api_base() -> str:
    """Canonical SearXNG URL for the current deployment topology."""
    if is_running_inside_docker():
        return SEARXNG_DOCKER_SERVICE_URL
    return SEARXNG_HOST_URL


def get_searxng_probe_candidate_urls() -> tuple[str, ...]:
    """URLs to probe, ordered by likelihood for the current topology."""
    if is_running_inside_docker():
        return (SEARXNG_DOCKER_SERVICE_URL, SEARXNG_HOST_URL, "http://localhost:8081")
    return SEARXNG_PROBE_CANDIDATE_URLS


def reset_search_topology_cache_for_testing() -> None:
    """Clear cached topology detection (tests only)."""
    get_default_searxng_api_base.cache_clear()


__all__ = [
    "get_default_searxng_api_base",
    "get_searxng_probe_candidate_urls",
    "is_running_inside_docker",
    "reset_search_topology_cache_for_testing",
]
