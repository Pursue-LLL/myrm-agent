"""Unit tests for chrome_mcp_e2e helper utilities."""

from __future__ import annotations

import sys
import time
import urllib.error
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
    assert "_wait_mux_hand_probe_allowed" not in source
    assert "wait_mux_hand_probe_allowed" not in block
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
    loaded = _open_page_parallel_budgets(300.0, new_page_timeout_ms=120_000, peers=8)
    assert loaded[0] == 60.0
    assert loaded[1] == 120_000
    assert loaded[2] == 258.0
    assert loaded[3] == 460.0
    assert loaded[4] == 2


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
    monkeypatch.setattr(
        chrome_mcp_e2e, "_warm_ui_parallel_wait_sec", lambda base: base
    )
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
    from tests.support import chrome_mcp_e2e

    assert chrome_mcp_e2e._warm_ui_parallel_wait_sec(180.0) == 300.0
