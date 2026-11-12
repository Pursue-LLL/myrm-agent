"""Unit tests for the open_mcp_page budgets: attempt counts, body-wall caps, mux drain, new-page join timeouts."""

from __future__ import annotations

import sys
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    _open_page_attempt_count,
    _open_page_parallel_budgets,
    _shared_read_parallel_open_page_retry_allowed,
)


def test_open_page_cdp_probe_budget_scales_with_mux_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Load:
        wave_leases: int
        mux_contexts: int

    monkeypatch.setitem(
        sys.modules,
        "mux.load",
        type(
            "MuxLoadStub",
            (),
            {"snapshot_mux_load": staticmethod(lambda: _Load(wave_leases=5, mux_contexts=2))},
        )(),
    )
    from tests.support.chrome_mcp_e2e import _open_page_cdp_probe_budget_sec

    assert _open_page_cdp_probe_budget_sec() == 105.0


def test_retryable_open_page_error_includes_connection_reset() -> None:
    from tests.support.chrome_mcp_e2e import _retryable_open_page_error

    assert _retryable_open_page_error(RuntimeError("Chrome MCP connection reset during tools/call; retry this call"))


def test_open_page_parallel_budgets_scale_with_live_peer_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 0)
    idle = _open_page_parallel_budgets(300.0, new_page_timeout_ms=120_000, peers=3)
    assert idle == (60.0, 120_000, 150.0, 280.0, 2)

    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 6)
    monkeypatch.setattr(
        chrome_mcp_e2e,
        "_open_page_body_fraction_cap_sec",
        lambda: 210.0,
    )
    loaded = _open_page_parallel_budgets(300.0, new_page_timeout_ms=120_000, peers=8)
    assert loaded[0] == 60.0
    assert loaded[1] == 120_000
    assert loaded[2] == pytest.approx(115.5)
    assert loaded[3] == pytest.approx(210.0)
    assert loaded[4] == 1


def test_phase_c_burst_open_mcp_uses_signoff_parallel_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dev_gate.contract import signoff_open_mcp_budgets

    from tests.support import chrome_mcp_e2e

    monkeypatch.delenv("E2E_SIGNOFF", raising=False)
    monkeypatch.setenv("MYRM_E2E_PHASE_C_BURST_LANES", "4")
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 0)
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: False)
    expected = signoff_open_mcp_budgets(parallel_peers=4)
    result = _open_page_parallel_budgets(300.0, new_page_timeout_ms=120_000, peers=0)
    assert result[2] == expected.wall_budget_sec
    assert result[3] == expected.total_budget_sec
    assert result[4] == expected.attempt_count


def test_open_page_body_fraction_cap_scales_with_live_body_wall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.delenv("MYRM_E2E_SIGNOFF", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "mux.transport_supervisor",
        type(
            "TransportSupervisorStub",
            (),
            {
                "live_agent_body_wall_cap_sec": staticmethod(lambda: 720),
            },
        )(),
    )
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 0)
    assert chrome_mcp_e2e._open_page_body_fraction_cap_sec() == pytest.approx(252.0)


def test_open_page_queue_wait_extends_bootstrap_deadlines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(
        chrome_mcp_e2e,
        "_open_page_queue_wait_extends_deadlines",
        lambda: True,
    )
    started, wall, total = chrome_mcp_e2e._extend_open_page_deadlines_for_queue_wait(
        elapsed_sec=45.0,
        transport_session_started=100.0,
        wall_deadline=200.0,
        total_deadline=300.0,
    )
    assert started == 100.0
    assert wall == 245.0
    assert total == 345.0


def test_open_page_body_fraction_cap_scales_with_parallel_peers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_E2E_SIGNOFF", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "mux.transport_supervisor",
        type(
            "TransportSupervisorStub",
            (),
            {
                "live_agent_body_wall_cap_sec": staticmethod(lambda: 600),
            },
        )(),
    )
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 4)
    assert chrome_mcp_e2e._open_page_body_fraction_cap_sec() == pytest.approx(270.0)


def test_open_page_attempt_count_is_one_under_parallel_peers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 4)
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: False)
    assert chrome_mcp_e2e._open_page_attempt_count() == 1
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    assert chrome_mcp_e2e._open_page_attempt_count() == 2
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 3)
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    assert chrome_mcp_e2e._open_page_attempt_count() == 3
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 0)
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    assert chrome_mcp_e2e._open_page_attempt_count() == 2
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: False)
    assert chrome_mcp_e2e._open_page_attempt_count() == chrome_mcp_e2e._OPEN_PAGE_ATTEMPTS


def test_signoff_new_page_join_timeout_uses_mux_timeout_plus_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from tests.support import chrome_mcp_e2e

    captured: list[float] = []
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    monkeypatch.setattr(
        chrome_mcp_e2e,
        "_signoff_threaded_new_page",
        lambda client, url, *, timeout_ms, join_timeout_sec: captured.append(join_timeout_sec) or MagicMock(),
    )
    monkeypatch.setattr(
        "dev_gate.contract._parallel_signoff_pressure_peers",
        lambda: 0,
    )
    monkeypatch.setattr("mux.transport_supervisor.parallel_mux_peer_count", lambda: 0)
    monkeypatch.setattr(
        "mux.load.snapshot_mux_load",
        lambda **kwargs: type("_Snap", (), {"mux_contexts": 0, "wave_leases": 0})(),
    )
    monkeypatch.setattr(chrome_mcp_e2e, "_signoff_wait_mux_before_new_page", lambda **_: None)
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 0)
    client = MagicMock()
    chrome_mcp_e2e._open_page_new_page(
        client,
        "http://127.0.0.1:3000",
        timeout_ms=90_000,
        attempt_wall_deadline=time.monotonic() + 240.0,
    )
    from dev_gate.contract import signoff_new_page_join_timeout_sec

    assert captured == [signoff_new_page_join_timeout_sec(page_timeout_ms=90_000, parallel_peers=0)]


def test_signoff_new_page_join_timeout_scales_under_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from unittest.mock import MagicMock

    from tests.support import chrome_mcp_e2e

    captured: list[float] = []
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    monkeypatch.setattr(
        chrome_mcp_e2e,
        "_signoff_threaded_new_page",
        lambda client, url, *, timeout_ms, join_timeout_sec: captured.append(join_timeout_sec) or MagicMock(),
    )
    monkeypatch.setattr(
        "dev_gate.contract._parallel_signoff_pressure_peers",
        lambda: 3,
    )
    monkeypatch.setattr("mux.transport_supervisor.parallel_mux_peer_count", lambda: 3)
    monkeypatch.setattr(
        "mux.load.snapshot_mux_load",
        lambda **kwargs: type("_Snap", (), {"mux_contexts": 3, "wave_leases": 3})(),
    )
    monkeypatch.setattr(chrome_mcp_e2e, "_signoff_wait_mux_before_new_page", lambda **_: None)
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 3)
    client = MagicMock()
    chrome_mcp_e2e._open_page_new_page(
        client,
        "http://127.0.0.1:3000",
        timeout_ms=90_000,
        attempt_wall_deadline=time.monotonic() + 240.0,
    )
    from dev_gate.contract import signoff_new_page_join_timeout_sec

    assert captured == [signoff_new_page_join_timeout_sec(page_timeout_ms=90_000, parallel_peers=3)]


def test_signoff_mux_drain_budget_uses_bootstrap_remaining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 0)
    monkeypatch.setattr(
        chrome_mcp_e2e,
        "_mux_cold_attach_drain_budget_sec",
        lambda: 57.0,
    )
    monkeypatch.setattr(
        "e2e_session_runtime.lifecycle.current_phase",
        lambda: "bootstrap",
    )
    monkeypatch.setattr(
        "e2e_session_runtime.lifecycle.remaining_wall_sec",
        lambda: 387.0,
    )
    assert chrome_mcp_e2e._signoff_mux_drain_budget_sec() == 57.0


def test_signoff_mux_drain_budget_parallel_skips_bootstrap_remaining_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 2)
    monkeypatch.setattr(
        chrome_mcp_e2e,
        "_mux_cold_attach_drain_budget_sec",
        lambda: 69.0,
    )
    monkeypatch.setattr(
        "e2e_session_runtime.lifecycle.current_phase",
        lambda: "bootstrap",
    )
    monkeypatch.setattr(
        "e2e_session_runtime.lifecycle.remaining_wall_sec",
        lambda: 45.0,
    )
    assert chrome_mcp_e2e._signoff_mux_drain_budget_sec() >= 69.0


def test_shared_read_parallel_open_page_retry_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_E2E_LANE", "READ")
    monkeypatch.delenv("MYRM_E2E_SHARED_HOT", raising=False)
    assert _shared_read_parallel_open_page_retry_allowed() is True
    monkeypatch.setenv("MYRM_E2E_SHARED_HOT", "1")
    assert _shared_read_parallel_open_page_retry_allowed() is False


def test_open_page_attempt_count_allows_read_lane_parallel_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setenv("MYRM_E2E_LANE", "READ")
    monkeypatch.delenv("MYRM_E2E_SHARED_HOT", raising=False)
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 4)
    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: False)
    monkeypatch.setattr(chrome_mcp_e2e, "_dev_private_shpoib_bootstrap_phase", lambda: False)
    assert _open_page_attempt_count() == 2
