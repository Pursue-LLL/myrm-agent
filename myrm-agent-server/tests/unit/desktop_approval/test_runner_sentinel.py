"""Unit tests for the desktop approval mid-run Accessibility sentinel."""

from __future__ import annotations

import pytest

from tests.e2e.desktop_approval import runner as approval_runner


@pytest.fixture()
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _sec: None)


def _patch_probe(monkeypatch: pytest.MonkeyPatch, behavior: object) -> dict[str, int]:
    calls = {"count": 0}

    def _fake() -> dict[str, object]:
        calls["count"] += 1
        if isinstance(behavior, BaseException):
            raise behavior
        assert isinstance(behavior, dict)
        return behavior

    monkeypatch.setattr(approval_runner, "desktop_permissions", _fake)
    return calls


def test_sentinel_skips_probe_when_initially_ungranted(
    monkeypatch: pytest.MonkeyPatch, no_sleep: None
) -> None:
    calls = _patch_probe(monkeypatch, {"accessibility": False})
    assert approval_runner._backend_lost_ax_mid_run(False) is False
    assert calls["count"] == 0


def test_sentinel_healthy_on_first_probe(
    monkeypatch: pytest.MonkeyPatch, no_sleep: None
) -> None:
    calls = _patch_probe(monkeypatch, {"accessibility": True})
    assert approval_runner._backend_lost_ax_mid_run(True) is False
    assert calls["count"] == 1


def test_sentinel_confirms_loss_with_two_probes(
    monkeypatch: pytest.MonkeyPatch, no_sleep: None
) -> None:
    calls = _patch_probe(monkeypatch, {"accessibility": False})
    assert approval_runner._backend_lost_ax_mid_run(True) is True
    assert calls["count"] == 2


def test_sentinel_fails_open_on_empty_payload(
    monkeypatch: pytest.MonkeyPatch, no_sleep: None
) -> None:
    calls = _patch_probe(monkeypatch, {})
    assert approval_runner._backend_lost_ax_mid_run(True) is False
    assert calls["count"] == 1


def test_sentinel_fails_open_on_transport_error(
    monkeypatch: pytest.MonkeyPatch, no_sleep: None
) -> None:
    calls = _patch_probe(monkeypatch, OSError("backend down"))
    assert approval_runner._backend_lost_ax_mid_run(True) is False
    assert calls["count"] == 1


def test_sentinel_fails_open_on_malformed_payload(
    monkeypatch: pytest.MonkeyPatch, no_sleep: None
) -> None:
    calls = _patch_probe(monkeypatch, ValueError("non-JSON body"))
    assert approval_runner._backend_lost_ax_mid_run(True) is False
    assert calls["count"] == 1
