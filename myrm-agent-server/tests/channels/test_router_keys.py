"""Tests for routing_session_key."""

from __future__ import annotations

from app.channels.routing.router_keys import routing_session_key


def test_routing_session_key_format() -> None:
    assert routing_session_key("telegram", "123") == "telegram:123"


def test_routing_session_key_empty_peer_allowed() -> None:
    assert routing_session_key("x", "") == "x:"
