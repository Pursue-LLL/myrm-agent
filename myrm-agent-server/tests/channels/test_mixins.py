"""Tests for core/mixins.py — CachedGroupMixin."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from app.channels.core.mixins import CachedGroupMixin


@dataclass
class _FakeGroup:
    jid: str
    name: str


class _FakeChannel(CachedGroupMixin):
    """Minimal stub combining CachedGroupMixin with required attributes."""

    def __init__(self, ttl: float = 300.0) -> None:
        CachedGroupMixin.__init__(self, groups_cache_ttl=ttl)
        self._name = "test_channel"
        self.emit = MagicMock()


class TestCachedGroupMixin:
    def test_cache_initially_invalid(self) -> None:
        ch = _FakeChannel()
        assert ch._is_groups_cache_valid(force_refresh=False) is False

    def test_cache_valid_after_update(self) -> None:
        ch = _FakeChannel()
        groups = [_FakeGroup(jid="g1", name="Group 1")]
        ch._update_groups_cache(groups)  # type: ignore[arg-type]
        assert ch._is_groups_cache_valid(force_refresh=False) is True

    def test_force_refresh_invalidates(self) -> None:
        ch = _FakeChannel()
        groups = [_FakeGroup(jid="g1", name="Group 1")]
        ch._update_groups_cache(groups)  # type: ignore[arg-type]
        assert ch._is_groups_cache_valid(force_refresh=True) is False

    def test_update_emits_on_change(self) -> None:
        ch = _FakeChannel()
        g1 = [_FakeGroup(jid="g1", name="A")]
        ch._update_groups_cache(g1)  # type: ignore[arg-type]
        ch.emit.assert_called_once_with("groups_change", g1)

    def test_update_no_emit_when_same_jids(self) -> None:
        ch = _FakeChannel()
        g1 = [_FakeGroup(jid="g1", name="A")]
        ch._update_groups_cache(g1)  # type: ignore[arg-type]
        ch.emit.reset_mock()

        g1_updated = [_FakeGroup(jid="g1", name="A renamed")]
        ch._update_groups_cache(g1_updated)  # type: ignore[arg-type]
        ch.emit.assert_not_called()

    def test_update_emits_on_jid_change(self) -> None:
        ch = _FakeChannel()
        ch._update_groups_cache([_FakeGroup(jid="g1", name="A")])  # type: ignore[arg-type]
        ch.emit.reset_mock()

        ch._update_groups_cache([_FakeGroup(jid="g2", name="B")])  # type: ignore[arg-type]
        ch.emit.assert_called_once()

    def test_clear_groups(self) -> None:
        ch = _FakeChannel()
        ch._update_groups_cache([_FakeGroup(jid="g1", name="A")])  # type: ignore[arg-type]
        ch.emit.reset_mock()

        ch._update_groups_cache([])  # type: ignore[arg-type]
        ch.emit.assert_called_once_with("groups_change", [])
        assert ch._groups_cache == []

    def test_clear_empty_noop(self) -> None:
        ch = _FakeChannel()
        ch._update_groups_cache([])  # type: ignore[arg-type]
        ch.emit.assert_not_called()

    def test_cache_metrics(self) -> None:
        ch = _FakeChannel(ttl=60.0)
        metrics = ch._get_groups_cache_metrics()
        assert metrics["cache_size"] == 0
        assert metrics["is_valid"] is False

        ch._update_groups_cache([_FakeGroup(jid="g1", name="A")])  # type: ignore[arg-type]
        metrics = ch._get_groups_cache_metrics()
        assert metrics["cache_size"] == 1
        assert metrics["is_valid"] is True
        assert metrics["ttl_remaining_seconds"] > 0

    def test_cache_expired(self) -> None:
        ch = _FakeChannel(ttl=0.0)
        ch._update_groups_cache([_FakeGroup(jid="g1", name="A")])  # type: ignore[arg-type]
        assert ch._is_groups_cache_valid(force_refresh=False) is False
