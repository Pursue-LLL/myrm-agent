"""Unit tests for the warm-UI helpers: route warm-up, shared-UI wait scaling and the hydrate slot."""

from __future__ import annotations

import sys
import urllib.error
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.support.chrome_mcp_e2e import parallel_load, warm_ui_route
from tests.support.chrome_mcp_e2e.patching import patch_everywhere


def test_warm_ui_route_retries_until_shared_ui_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The third GET succeeds, so the window only bounds a broken retry loop and must stay far above any host stall.
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "60")
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "0.01")
    # The registry-reuse shortcut, the peer count and the hydrate-queue decision probe the host with git and ps; the
    # retry loop needs none of them.
    monkeypatch.setattr("e2e_core.warm_shell_registry.platform_shell_fresh", lambda **_: False)
    monkeypatch.setattr("mux.transport_supervisor.parallel_active_test_count", lambda: 0)
    patch_everywhere(monkeypatch, "parallel_shared_ui_hydrate_queue_enabled", lambda: False)
    patch_everywhere(monkeypatch, "_warm_ui_parallel_wait_sec", lambda base: base)
    patch_everywhere(monkeypatch, "heal_shared_frontend_debounced", lambda *args, **kwargs: None)
    attempts = {"count": 0}

    class _FakeResponse:
        status = 200

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def _urlopen(request: object, timeout: float = 30.0) -> _FakeResponse:
        del request, timeout
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise urllib.error.URLError("connection refused")
        return _FakeResponse()

    patch_everywhere(monkeypatch, "get_e2e_ui_url", MagicMock(return_value="http://127.0.0.1:3000"))
    with patch("urllib.request.urlopen", side_effect=_urlopen):
        warm_ui_route("/")
    assert attempts["count"] == 3


def test_warm_ui_route_uses_shared_ui_hydrate_slot_when_shpoib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_SHPOIB", "1")
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "5")
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "0.01")
    patch_everywhere(monkeypatch, "_warm_ui_parallel_wait_sec", lambda base: base)
    patch_everywhere(monkeypatch, "heal_shared_frontend_debounced", lambda *args, **kwargs: None)
    slot_calls = {"count": 0}

    class _FakeResponse:
        status = 200

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    @contextmanager
    def _track_slot() -> Iterator[None]:
        slot_calls["count"] += 1
        yield

    patch_everywhere(monkeypatch, "shared_ui_hydrate_slot", _track_slot)
    # Isolate from live system wave load — the queue decision must be forced.
    patch_everywhere(
        monkeypatch,
        "parallel_shared_ui_hydrate_queue_enabled",
        lambda: True,
    )
    # Isolate from a real sealed shell record so the hydrate slot path runs.
    import e2e_core.warm_shell_registry as warm_shell_registry

    monkeypatch.setattr(
        warm_shell_registry,
        "platform_shell_fresh",
        lambda **kwargs: False,
    )

    patch_everywhere(monkeypatch, "get_e2e_ui_url", MagicMock(return_value="http://127.0.0.1:3000"))
    with patch("urllib.request.urlopen", return_value=_FakeResponse()):
        warm_ui_route("/")
    assert slot_calls["count"] == 1


def test_warm_ui_parallel_wait_sec_scales_with_active_leases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "180")

    class _FakePolicy:
        @staticmethod
        def wave_active_lease_count(_root: Path) -> int:
            return 4

    monkeypatch.setitem(
        sys.modules,
        "e2e_core.stack_mutation_policy",
        _FakePolicy(),  # type: ignore[arg-type]
    )

    class _FakeContract:
        @staticmethod
        def phase_c_burst_lane_count() -> int:
            return 0

        @staticmethod
        def shared_ui_hydrate_wait_sec() -> int:
            return 900

    monkeypatch.setitem(
        sys.modules,
        "e2e_core.shared_ui_hydrate",
        type(
            "_FakeHydrate",
            (),
            {"parallel_shared_ui_hydrate_queue_enabled": staticmethod(lambda: False)},
        )(),
    )
    monkeypatch.setitem(
        sys.modules,
        "dev_gate.contract",
        _FakeContract(),  # type: ignore[arg-type]
    )
    monkeypatch.setitem(
        sys.modules,
        "mux.transport_supervisor",
        type(
            "_FakeTransportSupervisor",
            (),
            {"parallel_active_test_count": staticmethod(lambda: 0)},
        )(),
    )

    assert parallel_load._warm_ui_parallel_wait_sec(180.0) == 360.0


def test_warm_ui_parallel_wait_sec_uses_parallel_active_test_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakePolicy:
        @staticmethod
        def wave_active_lease_count(_root: Path) -> int:
            return 2

    class _FakeTransport:
        @staticmethod
        def parallel_active_test_count() -> int:
            return 8

    class _FakeContract:
        @staticmethod
        def phase_c_burst_lane_count() -> int:
            return 0

        @staticmethod
        def shared_ui_hydrate_wait_sec() -> int:
            return 900

    monkeypatch.setitem(sys.modules, "e2e_core.stack_mutation_policy", _FakePolicy())  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "mux.transport_supervisor", _FakeTransport())  # type: ignore[arg-type]
    monkeypatch.setitem(
        sys.modules,
        "e2e_core.shared_ui_hydrate",
        type(
            "_FakeHydrate",
            (),
            {"parallel_shared_ui_hydrate_queue_enabled": staticmethod(lambda: False)},
        )(),
    )
    monkeypatch.setitem(sys.modules, "dev_gate.contract", _FakeContract())  # type: ignore[arg-type]

    assert parallel_load._warm_ui_parallel_wait_sec(120.0) == 480.0


def test_warm_ui_parallel_wait_sec_skips_peer_scale_when_hydrate_queue_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_PHASE_C_BURST_LANES", "4")

    class _FakeHydrate:
        @staticmethod
        def parallel_shared_ui_hydrate_queue_enabled() -> bool:
            return True

    monkeypatch.setitem(
        sys.modules,
        "e2e_core.shared_ui_hydrate",
        _FakeHydrate(),  # type: ignore[arg-type]
    )

    assert parallel_load._warm_ui_parallel_wait_sec(30.0) == 30.0


def test_warm_ui_parallel_wait_sec_burst_uses_lane_width_not_foreign_peers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_PHASE_C_BURST_LANES", "4")

    class _FakeHydrate:
        @staticmethod
        def parallel_shared_ui_hydrate_queue_enabled() -> bool:
            return False

    class _FakePolicy:
        @staticmethod
        def wave_active_lease_count(_root: Path) -> int:
            return 2

    class _FakeTransport:
        @staticmethod
        def parallel_active_test_count() -> int:
            return 8

    class _FakeContract:
        @staticmethod
        def phase_c_burst_lane_count() -> int:
            return 4

        @staticmethod
        def shared_ui_hydrate_wait_sec() -> int:
            return 900

    monkeypatch.setitem(sys.modules, "e2e_core.shared_ui_hydrate", _FakeHydrate())  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "e2e_core.stack_mutation_policy", _FakePolicy())  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "mux.transport_supervisor", _FakeTransport())  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "dev_gate.contract", _FakeContract())  # type: ignore[arg-type]

    # 30 + 4*45 = 210 (burst lanes), not 30 + 8*45 = 390 (foreign peers)
    assert parallel_load._warm_ui_parallel_wait_sec(30.0) == 210.0
