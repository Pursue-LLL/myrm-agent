"""Start local SearXNG via Docker Compose (local / tauri deploy only)."""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.toolkits.web_search.local_probe import probe_searxng_endpoints

from app.startup.local_search_bootstrap import try_start_local_search_profile

logger = logging.getLogger(__name__)

_PROBE_AFTER_START_ATTEMPTS = 15
_PROBE_INTERVAL_S = 2.0


async def start_local_searxng_and_wait() -> dict[str, object]:
    """Run docker compose search profile, then poll until SearXNG responds or timeout."""
    started = await asyncio.to_thread(try_start_local_search_profile, blocking=True)
    if not started:
        return {
            "docker_invoked": False,
            "available": False,
            "base_url": "",
            "error": "Docker is not available or compose failed",
        }

    last_error: str | None = None
    for _ in range(_PROBE_AFTER_START_ATTEMPTS):
        await asyncio.sleep(_PROBE_INTERVAL_S)
        result = await probe_searxng_endpoints()
        if result.available:
            return {
                "docker_invoked": True,
                "available": True,
                "base_url": result.base_url,
                "latency_ms": result.latency_ms,
                "error": None,
            }
        last_error = result.error

    return {
        "docker_invoked": True,
        "available": False,
        "base_url": "",
        "error": last_error or "SearXNG did not become ready in time",
    }
