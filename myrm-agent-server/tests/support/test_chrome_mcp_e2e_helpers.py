"""Unit tests for chrome_mcp_e2e helper utilities."""

from __future__ import annotations

import sys
import time
import urllib.error
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.support.chrome_mcp_e2e import (
    _open_page_parallel_budgets,
    wait_for_state,
    warm_ui_route,
)


def test_open_mcp_page_applies_shpoib_bootstrap_without_initial_reload() -> None:
    source = Path(__file__).with_name("chrome_mcp_e2e.py").read_text(encoding="utf-8")
    block = source.split("def open_mcp_page", 1)[1].split("\ndef ", 1)[0]
    assert "_reapply_shpoib_runtime_after_reload" in block
    assert "client.reload" not in block
    reload_block = source.split("def reload_mcp_page", 1)[1].split("\ndef ", 1)[0]
    assert "client.reload" in reload_block
    assert "_reapply_shpoib_runtime_after_reload" in reload_block
    assert reload_block.index("client.reload") < reload_block.index(
        "_reapply_shpoib_runtime_after_reload"
    )
    assert "_blocking_progress_loop" in block
    assert "open_mcp_page_blocking" in block
    assert "wait_mux_hand_probe_allowed" in block
    assert "mux_upstream_wait_cap" in block
    assert block.index("wait_mux_hand_probe_allowed") < block.index(
        "transport_session_started = time.monotonic()"
    )
    assert "R156: runtime inject must not share sliced tool wall" in block
    assert block.index("set_tool_wall_deadline(None)") < block.index("binding_source")
    assert (
        "connection reset"
        in source.split("def _retryable_open_page_error", 1)[1].split("\ndef ", 1)[0]
    )


def test_sync_open_page_tool_wall_allocates_remaining_steps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e
    from tests.support.chrome_mcp_e2e import _sync_open_page_tool_wall

    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 0)
    client = MagicMock()
    now = time.monotonic()
    _sync_open_page_tool_wall(
        client,
        wall_deadline=now + 400.0,
        total_deadline=now + 400.0,
        steps_remaining=4,
        floor_sec=90.0,
    )
    deadline = client.set_tool_wall_deadline.call_args[0][0]
    assert deadline - now >= 89.0
    assert deadline - now <= 101.0


def test_sync_open_page_tool_wall_parallel_uses_total_deadline_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e
    from tests.support.chrome_mcp_e2e import _sync_open_page_tool_wall

    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 4)
    client = MagicMock()
    now = time.monotonic()
    total_deadline = now + 460.0
    _sync_open_page_tool_wall(
        client,
        wall_deadline=now + 258.0,
        total_deadline=total_deadline,
        steps_remaining=4,
        floor_sec=90.0,
    )
    assert client.set_tool_wall_deadline.call_args[0][0] == total_deadline


def test_refresh_signoff_open_nav_tool_wall_restores_bootstrap_remaining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    from tests.support import chrome_mcp_e2e
    from tests.support.chrome_mcp_e2e import _refresh_signoff_open_nav_tool_wall

    @dataclass(frozen=True)
    class _Budgets:
        layout_wait_sec: float = 120.0
        wall_budget_sec: float = 210.0

    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 4)
    monkeypatch.setitem(
        sys.modules,
        "dev_gate_contract",
        type(
            "DevGateContractStub",
            (),
            {"signoff_open_mcp_budgets": staticmethod(lambda **_: _Budgets())},
        )(),
    )
    monkeypatch.setitem(
        sys.modules,
        "e2e_session_lifecycle",
        type(
            "LifecycleStub",
            (),
            {
                "current_phase": staticmethod(lambda: "bootstrap"),
                "remaining_wall_sec": staticmethod(lambda: 175.0),
            },
        )(),
    )
    client = MagicMock()
    now = time.monotonic()
    _refresh_signoff_open_nav_tool_wall(
        client,
        wall_deadline=now + 4.0,
        total_deadline=now + 4.0,
    )
    deadline = client.set_tool_wall_deadline.call_args[0][0]
    assert 170.0 <= deadline - now <= 180.0


def test_refresh_signoff_open_nav_tool_wall_noop_outside_signoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e
    from tests.support.chrome_mcp_e2e import _refresh_signoff_open_nav_tool_wall

    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: False)
    client = MagicMock()
    now = time.monotonic()
    _refresh_signoff_open_nav_tool_wall(
        client,
        wall_deadline=now + 100.0,
        total_deadline=now + 100.0,
    )
    client.set_tool_wall_deadline.assert_not_called()


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
        "mux_load",
        type(
            "MuxLoadStub",
            (),
            {
                "snapshot_mux_load": staticmethod(
                    lambda: _Load(wave_leases=5, mux_contexts=2)
                )
            },
        )(),
    )
    from tests.support.chrome_mcp_e2e import _open_page_cdp_probe_budget_sec

    assert _open_page_cdp_probe_budget_sec() == 105.0


def test_retryable_open_page_error_includes_connection_reset() -> None:
    from tests.support.chrome_mcp_e2e import _retryable_open_page_error

    assert _retryable_open_page_error(
        RuntimeError("Chrome MCP connection reset during tools/call; retry this call")
    )


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


def test_open_page_body_fraction_cap_scales_with_live_body_wall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.delenv("MYRM_E2E_SIGNOFF", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "transport_supervisor",
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


def test_wait_for_state_parses_json_string_ready() -> None:
    client = MagicMock()
    page = MagicMock()
    client.evaluate.return_value = '{"ready": true, "text": "ok"}'

    result = wait_for_state(client, page, "(() => ({}))()", timeout_sec=1.0)

    assert result["ready"] is True
    assert result["text"] == "ok"


def test_warm_ui_route_retries_until_shared_ui_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "5")
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "0.01")
    monkeypatch.setattr(chrome_mcp_e2e, "_warm_ui_parallel_wait_sec", lambda base: base)
    monkeypatch.setattr(
        chrome_mcp_e2e, "heal_shared_frontend_debounced", lambda *args, **kwargs: None
    )
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

    with patch(
        "tests.support.chrome_mcp_e2e.get_e2e_ui_url",
        return_value="http://127.0.0.1:3000",
    ):
        with patch("urllib.request.urlopen", side_effect=_urlopen):
            warm_ui_route("/")
    assert attempts["count"] == 3


def test_warm_ui_route_uses_shared_ui_hydrate_slot_when_shpoib(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setenv("MYRM_E2E_SHPOIB", "1")
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "5")
    monkeypatch.setenv("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "0.01")
    monkeypatch.setattr(chrome_mcp_e2e, "_warm_ui_parallel_wait_sec", lambda base: base)
    monkeypatch.setattr(
        chrome_mcp_e2e, "heal_shared_frontend_debounced", lambda *args, **kwargs: None
    )
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

    monkeypatch.setattr(chrome_mcp_e2e, "shared_ui_hydrate_slot", _track_slot)

    with patch(
        "tests.support.chrome_mcp_e2e.get_e2e_ui_url",
        return_value="http://127.0.0.1:3000",
    ):
        with patch("urllib.request.urlopen", return_value=_FakeResponse()):
            warm_ui_route("/")
    assert slot_calls["count"] == 1


def test_blocking_progress_loop_emits_transport_progress_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "_PROGRESS_HEARTBEAT_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(chrome_mcp_e2e, "_TRANSPORT_PROGRESS_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(chrome_mcp_e2e, "heartbeat_e2e_lease", lambda: None)
    monkeypatch.setattr(chrome_mcp_e2e, "touch_wall_progress", lambda **_: None)
    import e2e_stall_guard

    monkeypatch.setattr(
        e2e_stall_guard, "assert_transport_node_not_stuck", lambda **_: None
    )

    with chrome_mcp_e2e._blocking_progress_loop(current_node="open_mcp_page_blocking"):
        time.sleep(0.05)

    captured = capsys.readouterr()
    assert "E2E_TRANSPORT_PROGRESS" in captured.err
    assert "open_mcp_page_blocking" in captured.err


def test_open_page_body_fraction_cap_scales_with_parallel_peers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_E2E_SIGNOFF", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "transport_supervisor",
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


def test_blocking_progress_loop_stall_sends_sigint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "_PROGRESS_HEARTBEAT_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(
        chrome_mcp_e2e,
        "_open_page_parallel_budgets",
        lambda *args, **kwargs: (60.0, 120_000, 30.0, 5.0, 2),
    )
    monkeypatch.setattr(chrome_mcp_e2e, "heartbeat_e2e_lease", lambda: None)
    monkeypatch.setattr(chrome_mcp_e2e, "touch_wall_progress", lambda **_: None)

    import e2e_stall_guard

    def _stall(**_: object) -> None:
        raise RuntimeError("MUX_RECLAIM_STALL: open_mcp_page_blocking blocked")

    monkeypatch.setattr(e2e_stall_guard, "assert_transport_node_not_stuck", _stall)

    import os
    import signal

    real_kill = os.kill
    sigint_calls: list[int] = []

    def _record_sigint(pid: int, sig: int) -> None:
        if sig == signal.SIGINT:
            sigint_calls.append(sig)
            return
        if sig == 0:
            return
        real_kill(pid, sig)

    monkeypatch.setattr("os.kill", _record_sigint)

    with chrome_mcp_e2e._blocking_progress_loop(current_node="open_mcp_page_blocking"):
        time.sleep(0.05)

    assert sigint_calls == [2]  # signal.SIGINT


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
        "stack_mutation_policy",
        _FakePolicy(),  # type: ignore[arg-type]
    )

    class _FakeContract:
        @staticmethod
        def shared_ui_hydrate_wait_sec() -> int:
            return 900

    monkeypatch.setitem(
        sys.modules,
        "dev_gate_contract",
        _FakeContract(),  # type: ignore[arg-type]
    )
    from tests.support import chrome_mcp_e2e

    assert chrome_mcp_e2e._warm_ui_parallel_wait_sec(180.0) == 360.0


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
    assert (
        chrome_mcp_e2e._open_page_attempt_count() == chrome_mcp_e2e._OPEN_PAGE_ATTEMPTS
    )


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
        lambda client, url, *, timeout_ms, join_timeout_sec: (
            captured.append(join_timeout_sec) or MagicMock()
        ),
    )
    monkeypatch.setattr(
        "dev_gate_contract._parallel_signoff_pressure_peers",
        lambda: 0,
    )
    monkeypatch.setattr(chrome_mcp_e2e, "_signoff_wait_mux_before_new_page", lambda **_: None)
    client = MagicMock()
    chrome_mcp_e2e._open_page_new_page(
        client,
        "http://127.0.0.1:3000",
        timeout_ms=90_000,
        attempt_wall_deadline=time.monotonic() + 240.0,
    )
    assert captured == [95.0]


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
        lambda client, url, *, timeout_ms, join_timeout_sec: (
            captured.append(join_timeout_sec) or MagicMock()
        ),
    )
    monkeypatch.setattr(
        "dev_gate_contract._parallel_signoff_pressure_peers",
        lambda: 3,
    )
    monkeypatch.setattr(chrome_mcp_e2e, "_signoff_wait_mux_before_new_page", lambda **_: None)
    client = MagicMock()
    chrome_mcp_e2e._open_page_new_page(
        client,
        "http://127.0.0.1:3000",
        timeout_ms=90_000,
        attempt_wall_deadline=time.monotonic() + 240.0,
    )
    assert captured == [165.0]


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
        "e2e_session_lifecycle.current_phase",
        lambda: "bootstrap",
    )
    monkeypatch.setattr(
        "e2e_session_lifecycle.remaining_wall_sec",
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
        "e2e_session_lifecycle.current_phase",
        lambda: "bootstrap",
    )
    monkeypatch.setattr(
        "e2e_session_lifecycle.remaining_wall_sec",
        lambda: 45.0,
    )
    assert chrome_mcp_e2e._signoff_mux_drain_budget_sec() >= 69.0

