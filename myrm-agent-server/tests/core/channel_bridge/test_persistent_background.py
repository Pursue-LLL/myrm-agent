"""Tests for persistent background work metadata helpers."""

from app.core.channel_bridge.persistent_background import (
    BACKGROUND_SOURCE_BTW,
    BACKGROUND_SOURCE_VOICE,
    is_persistent_background,
)


def test_is_persistent_background_btw() -> None:
    assert is_persistent_background({"background_source": BACKGROUND_SOURCE_BTW}) is True


def test_is_persistent_background_voice() -> None:
    assert is_persistent_background({"background_source": BACKGROUND_SOURCE_VOICE}) is True


def test_is_persistent_background_unknown() -> None:
    assert is_persistent_background({"background_source": "cron"}) is False
    assert is_persistent_background({}) is False
    assert is_persistent_background(None) is False
