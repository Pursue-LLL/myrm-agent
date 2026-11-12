"""Unit tests for the open_mcp_page tool-wall deadline helpers."""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock

import pytest


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
        "dev_gate.contract",
        type(
            "DevGateContractStub",
            (),
            {"signoff_open_mcp_budgets": staticmethod(lambda **_: _Budgets())},
        )(),
    )
    monkeypatch.setitem(
        sys.modules,
        "e2e_session_runtime.lifecycle",
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


def test_refresh_signoff_open_nav_tool_wall_grants_nav_slice_when_mux_queue_exhausted_attempt_wall(
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
    monkeypatch.setattr(chrome_mcp_e2e, "_parallel_open_page_peer_count", lambda: 5)
    monkeypatch.setitem(
        sys.modules,
        "dev_gate.contract",
        type(
            "DevGateContractStub",
            (),
            {"signoff_open_mcp_budgets": staticmethod(lambda **_: _Budgets())},
        )(),
    )
    monkeypatch.setitem(
        sys.modules,
        "e2e_session_runtime.lifecycle",
        type(
            "LifecycleStub",
            (),
            {
                "current_phase": staticmethod(lambda: "body"),
                "remaining_wall_sec": staticmethod(lambda: 0.0),
            },
        )(),
    )
    client = MagicMock()
    now = time.monotonic()
    _refresh_signoff_open_nav_tool_wall(
        client,
        wall_deadline=now - 60.0,
        total_deadline=now - 30.0,
    )
    deadline = client.set_tool_wall_deadline.call_args[0][0]
    assert deadline - now >= 115.0


def test_sync_open_page_tool_wall_signoff_skips_immediate_expiry_when_attempt_wall_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import chrome_mcp_e2e
    from tests.support.chrome_mcp_e2e import _sync_open_page_tool_wall

    monkeypatch.setattr(chrome_mcp_e2e, "is_e2e_signoff_runtime", lambda: True)
    client = MagicMock()
    now = time.monotonic()
    _sync_open_page_tool_wall(
        client,
        wall_deadline=now - 10.0,
        total_deadline=now - 5.0,
        steps_remaining=1,
    )
    client.set_tool_wall_deadline.assert_not_called()


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
