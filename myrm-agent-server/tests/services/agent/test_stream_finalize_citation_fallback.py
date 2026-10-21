"""Verify memory citation fallback persistence helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.agent.streaming_support.citation_persistence import merge_memory_citation_fallback


def test_merge_memory_citation_fallback_skips_when_collector_has_ids() -> None:
    extra_data: dict[str, object] = {"citedMemoryIds": ["existing-id"]}

    with patch("myrm_agent_harness.api.hooks.get_memory_manager") as get_manager:
        merge_memory_citation_fallback(extra_data)
        get_manager.assert_not_called()

    assert extra_data["citedMemoryIds"] == ["existing-id"]


def test_merge_memory_citation_fallback_uses_memory_manager_ids() -> None:
    extra_data: dict[str, object] = {}
    manager = MagicMock()
    manager.last_cited_memory_ids = ["mem-a", "mem-b"]

    with patch("myrm_agent_harness.api.hooks.get_memory_manager", return_value=manager):
        merge_memory_citation_fallback(extra_data)

    assert extra_data["citedMemoryIds"] == ["mem-a", "mem-b"]
