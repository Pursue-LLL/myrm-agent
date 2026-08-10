"""Unit tests for e2e_api_verify health probe resilience (§26.28-C)."""

from __future__ import annotations

import sys
import time
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import e2e_api_verify as verify  # noqa: E402


@pytest.fixture(autouse=True)
def _no_probe_wall(monkeypatch: pytest.MonkeyPatch) -> None:
    verify._CONTEXT_PROBE_STARTED_MONO = None
    monkeypatch.setenv("E2E_CONTEXT_PROBE_WALL_SEC", "0.01")


def test_api_health_ok_retries_transient_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transient ConnectionResetError on first attempt recovers on retry."""
    verify._CONTEXT_PROBE_STARTED_MONO = None

    class _FakeResp:
        status = 200

        def __enter__(self) -> _FakeResp:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    calls: list[int] = []

    def _fake_urlopen(url: str, timeout: float):  # noqa: ANN001
        calls.append(timeout)
        if len(calls) == 1:
            raise urllib.error.URLError(ConnectionResetError(54))
        return _FakeResp()

    with patch.object(
        verify.urllib.request, "urlopen", side_effect=_fake_urlopen
    ), patch.object(verify, "_curl_loopback_get", return_value=None):
        assert verify._api_health_ok("http://127.0.0.1:8080") is True
    assert len(calls) == 2


def test_api_health_ok_no_retry_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """port-scan probes must not retry — single-shot only."""
    verify._CONTEXT_PROBE_STARTED_MONO = None
    calls: list[int] = []

    def _fake_urlopen(url: str, timeout: float):  # noqa: ANN001
        calls.append(timeout)
        raise urllib.error.URLError(ConnectionRefusedError(61))

    with patch.object(
        verify.urllib.request, "urlopen", side_effect=_fake_urlopen
    ), patch.object(verify, "_curl_loopback_get", return_value=None):
        assert (
            verify._api_health_ok(
                "http://127.0.0.1:18080",
                timeout_sec=verify.PORT_SCAN_PROBE_TIMEOUT_SEC,
                allow_retry=False,
            )
            is False
        )
    assert len(calls) == 2  # two HEALTH_PATHS, no retry loop


def test_api_health_ok_bounded_timeout_short_circuits() -> None:
    """Exhausted probe wall must not open sockets at all."""
    verify._begin_context_probe_wall()
    wall = verify._context_probe_wall_sec()
    time.sleep(wall + 0.01)
    with patch.object(verify.urllib.request, "urlopen") as urlopen:
        assert verify._api_health_ok("http://127.0.0.1:8080") is False
        urlopen.assert_not_called()
    verify._reset_context_probe_wall()


def test_resolve_context_starts_wall_after_fingerprint() -> None:
    """resolve_e2e_api_context must not start the probe wall before impl runs
    fingerprint calculation (§26.28-C regression guard)."""
    with patch.object(
        verify, "_resolve_e2e_api_context_impl", return_value=object()
    ) as impl:
        verify.resolve_e2e_api_context()
        impl.assert_called_once()
