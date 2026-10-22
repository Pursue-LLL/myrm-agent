"""Unit tests for the PTC MCP result-cache policy."""

from __future__ import annotations

from types import SimpleNamespace

from myrm_agent_harness.agent.skills.mcp.cache_policy import (
    READ_ONLY_CACHE_TTL_SECONDS,
    resolve_cache_ttl,
)


def _meta(config: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(mcp=SimpleNamespace(config=[config]))


def test_read_only_defaults_to_sixty_seconds() -> None:
    assert resolve_cache_ttl(_meta({}), "ping", is_read_only=True) == READ_ONLY_CACHE_TTL_SECONDS


def test_mutating_tool_is_never_cached() -> None:
    assert resolve_cache_ttl(_meta({}), "create_issue", is_read_only=False) is None


def test_explicit_allowlist_caches_unannotated_tool() -> None:
    meta = _meta({"cacheable_tools": ["get_current_date"]})
    assert resolve_cache_ttl(meta, "get_current_date", is_read_only=False) == READ_ONLY_CACHE_TTL_SECONDS


def test_zero_ttl_disables_cache() -> None:
    meta = _meta({"cache_ttl_seconds": 0})
    assert resolve_cache_ttl(meta, "ping", is_read_only=True) is None


def test_positive_ttl_overrides_default() -> None:
    meta = _meta({"cache_ttl_seconds": 15})
    assert resolve_cache_ttl(meta, "ping", is_read_only=True) == 15
