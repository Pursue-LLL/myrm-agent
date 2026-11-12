"""Unit tests for chrome_mcp_e2e helper utilities."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.support import chrome_mcp_e2e
from tests.support.chrome_mcp_e2e import (
    _APP_LAYOUT_READY_JS,
    _SETTINGS_LAYOUT_READY_JS,
    _page_shell_ready_js_for_url,
    navigate_mcp_page,
    wait_for_state,
)


def test_page_shell_ready_js_selects_settings_layout_for_settings_routes() -> None:
    assert _page_shell_ready_js_for_url("http://127.0.0.1:3000/") == _APP_LAYOUT_READY_JS
    assert _page_shell_ready_js_for_url("http://127.0.0.1:3000/settings/extensionBridge") == _SETTINGS_LAYOUT_READY_JS
    assert "settings-layout" in _SETTINGS_LAYOUT_READY_JS
    assert "settings-deferred-loading" in _SETTINGS_LAYOUT_READY_JS
    assert "app-layout" not in _SETTINGS_LAYOUT_READY_JS


def test_reapply_shpoib_bootstrap_runs_after_navigate() -> None:
    """Navigation clears window globals; bootstrap evaluate must run after target load."""
    source = Path(__file__).with_name("chrome_mcp_e2e.py").read_text(encoding="utf-8")
    block = source.split("def _reapply_shpoib_runtime_after_reload", 1)[1].split("\ndef ", 1)[0]
    assert "MYRM_BROWSER_ORCHESTRATOR" not in block
    nav_idx = block.index("client.navigate(page, normalized_target")
    bootstrap_eval_idx = block.index("observed = client.evaluate(\n            page,\n            bootstrap_js,")
    assert nav_idx < bootstrap_eval_idx


def test_open_mcp_page_rpc_only_orchestrator_contract() -> None:
    """TAB-FINAL: open_mcp_page must delegate to orchestrator, not mux blocking."""
    source = Path(__file__).with_name("chrome_mcp_e2e.py").read_text(encoding="utf-8")
    block = source.split("def open_mcp_page", 1)[1].split("\ndef ", 1)[0]
    assert "_require_orchestrator_for_formal_e2e" in block
    assert "open_app_route_page" in block
    assert "complete_bootstrap_phase" in block
    assert block.index("complete_bootstrap_phase(phase_label=") < block.index("_ensure_orchestrator_shared_ui_session")
    assert "BROWSER_ORCHESTRATOR_REQUIRED" in block
    assert "open_mcp_page_blocking" not in block
    assert "ChromeMcpClient(request_timeout_sec=" not in block
    reload_block = source.split("def reload_mcp_page", 1)[1].split("\ndef ", 1)[0]
    assert "client.reload" in reload_block
    assert "_reapply_shpoib_runtime_after_reload" in reload_block
    assert "_is_isolated_stack()" in reload_block
    assert reload_block.index("client.reload") < reload_block.index("_reapply_shpoib_runtime_after_reload")


def test_e2e_nodes_cannot_start_body_before_owned_page_open() -> None:
    """The page helpers exclusively own the bootstrap-to-BODY transition."""
    e2e_dir = Path(__file__).parents[1] / "e2e"
    offenders = [
        path.name
        for path in e2e_dir.glob("test_*_chrome_e2e.py")
        if "complete_bootstrap_phase(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_wait_for_state_parses_json_string_ready() -> None:
    client = MagicMock()
    page = MagicMock()
    client.evaluate.return_value = '{"ready": true, "text": "ok"}'

    result = wait_for_state(client, page, "(() => ({}))()", timeout_sec=1.0)

    assert result["ready"] is True
    assert result["text"] == "ok"


def test_browser_operation_credit_slot_acquires_upstream_registry() -> None:
    source = (Path(__file__).resolve().parents[3] / "scripts/dev/lib/browser_orchestrator/core.py").read_text(encoding="utf-8")
    block = source.split("def browser_operation_credit_slot", 1)[1].split("\ndef ", 1)[0]
    assert "upstream_cold_attach_slot" in block


def test_blocking_progress_loop_emits_transport_progress_token(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tests.support import chrome_mcp_e2e

    monkeypatch.setattr(chrome_mcp_e2e, "_PROGRESS_HEARTBEAT_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(chrome_mcp_e2e, "_TRANSPORT_PROGRESS_INTERVAL_SEC", 0.01)
    monkeypatch.setattr(chrome_mcp_e2e, "heartbeat_once", lambda: None)
    monkeypatch.setattr(chrome_mcp_e2e, "touch_wall_progress", lambda **_: None)
    import e2e_core.stall_guard as e2e_stall_guard

    monkeypatch.setattr(e2e_stall_guard, "assert_transport_node_not_stuck", lambda **_: None)

    with chrome_mcp_e2e._blocking_progress_loop(current_node="open_mcp_page_blocking"):
        time.sleep(0.05)

    captured = capsys.readouterr()
    assert "E2E_TRANSPORT_PROGRESS" in captured.err
    assert "open_mcp_page_blocking" in captured.err


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
    monkeypatch.setattr(chrome_mcp_e2e, "heartbeat_once", lambda: None)
    monkeypatch.setattr(chrome_mcp_e2e, "touch_wall_progress", lambda **_: None)

    import e2e_core.stall_guard as e2e_stall_guard

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

    assert len(sigint_calls) >= 1
    assert all(sig == signal.SIGINT for sig in sigint_calls)


def test_warm_heal_guard_launch_force_before_debounced_call() -> None:
    """§26.31 / +: warm_ui heal skips launch-force only when the shared UI is reachable."""
    from pathlib import Path

    source = Path(__file__).resolve().parent / "chrome_mcp_e2e.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("def _heal_shared_frontend")
    block = text[start : start + 900]
    assert "launch_force_blocks_frontend_heal" in block
    assert block.index("launch_force_blocks_frontend_heal") < block.index("heal_shared_frontend_debounced")


class TestNavigateMcpPage:
    """An isolated stack navigates directly; only a shared stack with a private binding rebinds the page."""

    _TARGET = "http://127.0.0.1:3000/kanban"

    def test_an_isolated_stack_navigates_without_rebinding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_E2E_ISOLATED", "1")
        monkeypatch.setattr(chrome_mcp_e2e, "e2e_runtime_binding", lambda: {"runtimeId": "private"})
        rebind = MagicMock()
        monkeypatch.setattr(chrome_mcp_e2e, "_reapply_shpoib_runtime_after_reload", rebind)
        client = MagicMock()

        navigate_mcp_page(client, "page", self._TARGET, timeout_ms=5000)

        client.navigate.assert_called_once_with("page", self._TARGET, timeout_ms=5000)
        client.evaluate.assert_not_called()
        rebind.assert_not_called()

    def test_a_shared_stack_with_a_private_binding_rebinds_the_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_E2E_ISOLATED", raising=False)
        monkeypatch.setattr(chrome_mcp_e2e, "e2e_runtime_binding", lambda: {"runtimeId": "private"})
        rebind = MagicMock()
        monkeypatch.setattr(chrome_mcp_e2e, "_reapply_shpoib_runtime_after_reload", rebind)
        client = MagicMock()

        navigate_mcp_page(client, "page", self._TARGET, timeout_ms=5000)

        rebind.assert_called_once()
        assert rebind.call_args.kwargs["target_url"] == self._TARGET
        client.navigate.assert_not_called()
