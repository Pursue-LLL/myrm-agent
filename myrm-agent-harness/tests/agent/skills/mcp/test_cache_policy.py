"""Unit tests for the PTC MCP result-cache policy."""

from __future__ import annotations

from types import SimpleNamespace

from myrm_agent_harness.agent.skills.mcp.cache_policy import (
    resolve_cache_ttl,
)


def _meta(config: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(mcp=SimpleNamespace(config=[config]))


def test_no_config_means_no_cache() -> None:
    assert resolve_cache_ttl(_meta({}), "ping") is None


def test_allowlist_without_ttl_means_no_cache() -> None:
    meta = _meta({"cacheable_tools": ["get_current_date"]})
    assert resolve_cache_ttl(meta, "get_current_date") is None


def test_zero_ttl_disables_cache() -> None:
    meta = _meta({"cache_ttl_seconds": 0, "cacheable_tools": ["ping"]})
    assert resolve_cache_ttl(meta, "ping") is None


def test_positive_ttl_requires_allowlist() -> None:
    meta = _meta({"cache_ttl_seconds": 15})
    assert resolve_cache_ttl(meta, "ping") is None


def test_positive_ttl_with_allowlist() -> None:
    meta = _meta({"cache_ttl_seconds": 15, "cacheable_tools": ["ping"]})
    assert resolve_cache_ttl(meta, "ping") == 15


def test_allowlist_matches_prefixed_runtime_name() -> None:
    meta = _meta({"cache_ttl_seconds": 60, "cacheable_tools": ["get_tickets"]})
    assert resolve_cache_ttl(meta, "mcp__12306_mcp__get-tickets") == 60


def test_allowlist_matches_hyphenated_name() -> None:
    meta = _meta({"cache_ttl_seconds": 60, "cacheable_tools": ["get-tickets"]})
    assert resolve_cache_ttl(meta, "mcp__server__get_tickets") == 60


def test_clear_drops_default_and_custom_buckets() -> None:
    from myrm_agent_harness.agent.skills.mcp.cache_policy import CacheBuckets

    buckets = CacheBuckets()
    buckets.default.set("a", "value")
    buckets.get(30).set("b", "value")
    buckets.clear()
    assert buckets.default.get("a") is None
    assert buckets.get(30).get("b") is None
