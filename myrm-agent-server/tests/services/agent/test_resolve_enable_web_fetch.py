"""Tests for resolve_enable_web_fetch security gate."""

from __future__ import annotations

from app.services.agent.resolve_enable_web_fetch import resolve_enable_web_fetch


def test_resolve_enable_web_fetch_default_when_no_security() -> None:
    assert resolve_enable_web_fetch(None) is True


def test_resolve_enable_web_fetch_true_when_net_fetch_present() -> None:
    raw = {"capabilities": ["net_fetch", "file_read"]}
    assert resolve_enable_web_fetch(raw) is True


def test_resolve_enable_web_fetch_false_when_capabilities_omit_net_fetch() -> None:
    raw = {"capabilities": ["file_read"]}
    assert resolve_enable_web_fetch(raw) is False


def test_resolve_enable_web_fetch_true_when_capabilities_empty() -> None:
    assert resolve_enable_web_fetch({"capabilities": []}) is True
