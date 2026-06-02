"""Tests for _http_timeout.py — resolve_timeout and clamping."""

from __future__ import annotations

from app.channels.providers._http_timeout import (
    resolve_timeout,
)


class TestResolveTimeout:
    def test_default_value(self) -> None:
        assert resolve_timeout(15.0) == 15.0

    def test_override(self) -> None:
        assert resolve_timeout(15.0, 30.0) == 30.0

    def test_override_clamp_too_low(self) -> None:
        assert resolve_timeout(15.0, 0.1) == 1.0

    def test_override_clamp_too_high(self) -> None:
        assert resolve_timeout(15.0, 999.0) == 300.0

    def test_no_override(self) -> None:
        assert resolve_timeout(20.0, None) == 20.0

    def test_default_clamped(self) -> None:
        assert resolve_timeout(0.5) == 1.0
        assert resolve_timeout(500.0) == 300.0
