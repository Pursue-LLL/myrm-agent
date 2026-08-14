"""Unit tests for ChatUsageCache TTL debounce semantics.

Covers fresh hits, TTL expiry invalidation, last-message-id freshness keying,
bounded-entry eviction, and explicit invalidation.
"""

from __future__ import annotations

import time

from app.services.chat.usage_cache import ChatUsageCache


def test_missing_chat_returns_none() -> None:
    cache = ChatUsageCache()
    assert cache.get("chat-a", "m1") is None


def test_set_get_roundtrip() -> None:
    cache = ChatUsageCache()
    value = {"total_calls": 3, "total_tokens": 100, "total_usd": 0.1}
    cache.set("chat-a", "m1", value)
    assert cache.get("chat-a", "m1") == value


def test_get_after_ttl_expiry_returns_none() -> None:
    cache = ChatUsageCache(ttl_seconds=0.02)
    value = {"total_calls": 1, "total_tokens": 10, "total_usd": 0.01}
    cache.set("chat-a", "m1", value)
    time.sleep(0.05)
    assert cache.get("chat-a", "m1") is None


def test_get_with_stale_last_message_id_returns_none() -> None:
    cache = ChatUsageCache()
    cache.set("chat-a", "m1", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    assert cache.get("chat-a", "m2") is None
    assert cache.get("chat-a", None) is None


def test_set_overwrites_previous_value() -> None:
    cache = ChatUsageCache()
    cache.set("chat-a", "m1", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    new_value = {"total_calls": 2, "total_tokens": 2, "total_usd": 0.0}
    cache.set("chat-a", "m2", new_value)
    assert cache.get("chat-a", "m2") == new_value
    assert cache.get("chat-a", "m1") is None


def test_set_evicts_oldest_when_bounded() -> None:
    cache = ChatUsageCache(max_entries=2)
    cache.set("chat-a", "m1", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    cache.set("chat-b", "m2", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    cache.set("chat-c", "m3", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    # chat-a is the oldest -> evicted
    assert cache.get("chat-a", "m1") is None
    assert cache.get("chat-b", "m2") is not None
    assert cache.get("chat-c", "m3") is not None


def test_set_refreshes_timestamp_so_recent_entry_survives_eviction() -> None:
    cache = ChatUsageCache(max_entries=2)
    cache.set("chat-a", "m1", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    cache.set("chat-b", "m2", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    # Re-touch chat-a so it becomes the most recent
    cache.set("chat-a", "m1", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    cache.set("chat-c", "m3", {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0})
    assert cache.get("chat-b", "m2") is None
    assert cache.get("chat-a", "m1") is not None


def test_invalidate_clears_entry() -> None:
    cache = ChatUsageCache()
    value = {"total_calls": 1, "total_tokens": 1, "total_usd": 0.0}
    cache.set("chat-a", "m1", value)
    assert cache.get("chat-a", "m1") == value
    cache.invalidate("chat-a")
    assert cache.get("chat-a", "m1") is None
