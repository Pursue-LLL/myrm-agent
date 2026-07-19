"""Memory citation persistence helpers for agent stream finalize."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def merge_memory_citation_fallback(extra_data: dict[str, object]) -> None:
    """Backfill citedMemoryIds when SSE collector missed synthetic tool_end citation events."""
    if extra_data.get("citedMemoryIds"):
        return
    try:
        from myrm_agent_harness.api.hooks import get_memory_manager

        manager = get_memory_manager()
        ids = list(getattr(manager, "last_cited_memory_ids", []) or [])
        if ids:
            extra_data["citedMemoryIds"] = ids
    except Exception as exc:
        logger.debug("Memory citation fallback skipped: %s", exc)
