"""Unit tests for chrome_mcp_e2e helper utilities."""

from __future__ import annotations

import asyncio
import inspect
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.support.chrome_mcp_e2e import navigate_mcp_page, open_page, reload, wait_for_state, warm_ui
from tests.support.chrome_mcp_e2e.open_page_mux import _open_page_cdp_probe_budget_sec
from tests.support.chrome_mcp_e2e.patching import patch_everywhere
from tests.support.chrome_mcp_e2e.settings_wait import _SETTINGS_LAYOUT_READY_JS


def test_settings_layout_probe_waits_for_settings_layout_not_app_layout() -> None:
    assert "settings-layout" in _SETTINGS_LAYOUT_READY_JS
    assert "settings-deferred-loading" in _SETTINGS_LAYOUT_READY_JS
    assert "app-layout" not in _SETTINGS_LAYOUT_READY_JS


class TestOpenMcpPageSettingsLayoutWait:
    """Settings routes use SettingsLayout, not AppLayout: only they wait for the settings layout after the page opens."""

    _UI = "http://127.0.0.1:3000"

    @staticmethod
    def _open(monkeypatch: pytest.MonkeyPatch, url: str, *, skip_settings_layout_wait: bool = False) -> MagicMock:
        """Open ``url`` through ``open_mcp_page`` with the orchestrator faked; return the settings-layout wait spy."""
        monkeypatch.setenv("MYRM_BROWSER_ORCHESTRATOR", "1")
        client, page, settings_layout_wait = MagicMock(), MagicMock(), MagicMock()

        @contextmanager
        def _fake_open_app_route_page(*_args: object, **_kwargs: object) -> Iterator[tuple[MagicMock, MagicMock]]:
            yield client, page

        monkeypatch.setattr("browser_orchestrator.e2e.open_app_route_page", _fake_open_app_route_page)
        monkeypatch.setattr("e2e_session_runtime.lifecycle.complete_bootstrap_phase", MagicMock())
        patch_everywhere(monkeypatch, "_require_orchestrator_for_formal_e2e", lambda: None)
        patch_everywhere(monkeypatch, "_bounded_settings_ui_wait_sec", lambda base_sec: base_sec)
        patch_everywhere(monkeypatch, "_ensure_orchestrator_shared_ui_session", MagicMock())
        patch_everywhere(monkeypatch, "wait_for_settings_layout", settings_layout_wait)

        with open_page.open_mcp_page(url, skip_settings_layout_wait=skip_settings_layout_wait) as opened:
            assert opened == (client, page)
        return settings_layout_wait

    def test_a_settings_route_waits_for_the_settings_layout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        url = f"{self._UI}/settings/extensionBridge"

        settings_layout_wait = self._open(monkeypatch, url)

        settings_layout_wait.assert_called_once()
        assert settings_layout_wait.call_args.kwargs["page_url"] == url

    def test_the_settings_layout_wait_can_be_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings_layout_wait = self._open(monkeypatch, f"{self._UI}/settings/agents", skip_settings_layout_wait=True)

        settings_layout_wait.assert_not_called()

    def test_an_app_route_does_not_wait_for_the_settings_layout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings_layout_wait = self._open(monkeypatch, f"{self._UI}/")

        settings_layout_wait.assert_not_called()


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

    assert _open_page_cdp_probe_budget_sec() == 105.0


def test_reapply_shpoib_bootstrap_runs_after_navigate() -> None:
    """Navigation clears window globals; bootstrap evaluate must run after target load."""
    block = inspect.getsource(reload._reapply_shpoib_runtime_after_reload)
    assert "MYRM_BROWSER_ORCHESTRATOR" not in block
    nav_idx = block.index("client.navigate(page, normalized_target")
    bootstrap_eval_idx = block.index("observed = client.evaluate(\n            page,\n            bootstrap_js,")
    assert nav_idx < bootstrap_eval_idx


def test_open_mcp_page_rpc_only_orchestrator_contract() -> None:
    """TAB-FINAL: open_mcp_page must delegate to orchestrator, not mux blocking."""
    block = inspect.getsource(open_page.open_mcp_page)
    assert "_require_orchestrator_for_formal_e2e" in block
    assert "open_app_route_page" in block
    assert "complete_bootstrap_phase" in block
    assert block.index("complete_bootstrap_phase(phase_label=") < block.index("_ensure_orchestrator_shared_ui_session")
    assert "BROWSER_ORCHESTRATOR_REQUIRED" in block
    assert "open_mcp_page_blocking" not in block
    assert "ChromeMcpClient(request_timeout_sec=" not in block
    reload_block = inspect.getsource(reload.reload_mcp_page)
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


def test_warm_heal_guard_launch_force_before_debounced_call() -> None:
    """§26.31 / +: warm_ui heal skips launch-force only when the shared UI is reachable."""
    text = inspect.getsource(warm_ui)
    start = text.index("def _heal_shared_frontend")
    block = text[start : start + 900]
    assert "launch_force_blocks_frontend_heal" in block
    assert block.index("launch_force_blocks_frontend_heal") < block.index("heal_shared_frontend_debounced")


class TestNavigateMcpPage:
    """An isolated stack navigates directly; only a shared stack with a private binding rebinds the page."""

    _TARGET = "http://127.0.0.1:3000/kanban"

    def test_an_isolated_stack_navigates_without_rebinding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MYRM_E2E_ISOLATED", "1")
        patch_everywhere(monkeypatch, "e2e_runtime_binding", lambda: {"runtimeId": "private"})
        rebind = MagicMock()
        patch_everywhere(monkeypatch, "_reapply_shpoib_runtime_after_reload", rebind)
        client = MagicMock()

        navigate_mcp_page(client, "page", self._TARGET, timeout_ms=5000)

        client.navigate.assert_called_once_with("page", self._TARGET, timeout_ms=5000)
        client.evaluate.assert_not_called()
        rebind.assert_not_called()

    def test_a_shared_stack_with_a_private_binding_rebinds_the_page(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MYRM_E2E_ISOLATED", raising=False)
        patch_everywhere(monkeypatch, "e2e_runtime_binding", lambda: {"runtimeId": "private"})
        rebind = MagicMock()
        patch_everywhere(monkeypatch, "_reapply_shpoib_runtime_after_reload", rebind)
        client = MagicMock()

        navigate_mcp_page(client, "page", self._TARGET, timeout_ms=5000)

        rebind.assert_called_once()
        assert rebind.call_args.kwargs["target_url"] == self._TARGET
        client.navigate.assert_not_called()


class TestRunInIsolatedThreadLoop:
    """The shared-UI contract starts its own event loop although the calling thread may already run one."""

    def test_the_callable_runs_on_a_dedicated_thread(self) -> None:
        seen_threads: list[int] = []

        open_page._run_in_isolated_thread_loop(lambda: seen_threads.append(threading.get_ident()))

        assert seen_threads
        assert seen_threads[0] != threading.get_ident()

    def test_the_exception_of_the_callable_reaches_the_caller(self) -> None:
        failure = RuntimeError("shared UI contract failed")

        def _fail() -> None:
            raise failure

        with pytest.raises(RuntimeError) as raised:
            open_page._run_in_isolated_thread_loop(_fail)

        assert raised.value is failure

    def test_an_event_loop_starts_although_the_calling_thread_runs_one(self) -> None:
        started: list[str] = []

        async def _inner() -> None:
            started.append("inner loop")

        async def _caller() -> None:
            open_page._run_in_isolated_thread_loop(lambda: asyncio.run(_inner()))

        asyncio.run(_caller())

        assert started == ["inner loop"]
