"""E2E page lifecycle via Browser Orchestrator daemon (P0-B fail-closed path).

Used when ``MYRM_BROWSER_ORCHESTRATOR=1`` — no mux MCP fallback.
"""

from __future__ import annotations

import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from browser_orchestrator_client import BrowserOrchestratorClient
from cdp_chat_support import (
    e2e_api_base_inject_js,
    e2e_runtime_binding_source,
    get_e2e_api_url,
    get_open_page_api_url,
    wait_e2e_provider_ready,
)


@dataclass
class OrchestratorMcpPage:
    page_id: int
    target_id: str
    lease_id: str = ""
    context_id: str | None = None
    url: str | None = None


class OrchestratorChromeClient:
    """Minimal ChromeMcpClient duck-type for READ smokes over the daemon."""

    def __init__(
        self,
        *,
        session_id: str,
        daemon: BrowserOrchestratorClient,
        request_timeout_sec: float = 180.0,
    ) -> None:
        self._session_id = session_id
        self._daemon = daemon
        self._request_timeout_sec = request_timeout_sec

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def set_tool_wall_deadline(self, _deadline: float | None) -> None:
        return None

    def evaluate(
        self,
        page: OrchestratorMcpPage,
        expression: str,
        *,
        timeout_sec: float = 15.0,
    ) -> object:
        payload = self._daemon.evaluate_page(
            self._session_id,
            page.target_id,
            expression,
            timeout_sec=min(max(5.0, timeout_sec), self._request_timeout_sec),
        )
        return payload.get("value")

    def navigate(
        self,
        page: OrchestratorMcpPage,
        url: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
        _ = timeout_ms
        self._daemon.navigate_page(self._session_id, page.target_id, url)
        page.url = url

    def reload(self, page: OrchestratorMcpPage, *, timeout_ms: int = 15_000) -> None:
        _ = timeout_ms
        self.evaluate(
            page,
            "(() => { window.location.reload(); return true; })()",
            timeout_sec=min(30.0, max(5.0, timeout_ms / 1000.0)),
        )


def _resolve_session_id() -> str:
    from dev_gate_contract import E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN
    from chrome_e2e.gates.entry_guard import is_e2e_chrome_mcp_diagnostic_mode

    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    if run_id:
        return run_id
    agent_id = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if agent_id:
        return agent_id
    if is_e2e_chrome_mcp_diagnostic_mode():
        return f"orchestrator-diagnostic-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    raise RuntimeError(
        f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: MYRM_E2E_RUN_ID or "
        "MYRM_E2E_AGENT_ID required — launch via ./myrm test -m chrome_e2e"
    )


def _monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _spawn_ensure_orchestrator() -> None:
    """Best-effort daemon (re)start — serialized by ensure script flock."""
    script = _monorepo_root() / "scripts/dev/ensure-browser-orchestrator.sh"
    if not script.is_file():
        return
    env = os.environ.copy()
    env["MYRM_BROWSER_ORCHESTRATOR"] = "1"
    try:
        subprocess.run(
            ["bash", str(script)],
            env=env,
            timeout=45.0,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def _wait_orchestrator_daemon_ready(
    daemon: BrowserOrchestratorClient,
    *,
    wall_sec: float = 90.0,
) -> None:
    """Wait for daemon; invoke ensure script once after a short unreachable window."""
    deadline = time.monotonic() + wall_sec
    ensure_spawned = False
    while time.monotonic() < deadline:
        if daemon.is_alive():
            return
        elapsed = wall_sec - (deadline - time.monotonic())
        if not ensure_spawned and elapsed >= 8.0:
            _spawn_ensure_orchestrator()
            ensure_spawned = True
        time.sleep(0.5)
    raise RuntimeError(
        "BROWSER_ORCHESTRATOR_REQUIRED: daemon not running — "
        "run MYRM_BROWSER_ORCHESTRATOR=1 ./myrm ready --chrome"
    )


def _apply_orchestrator_shpoib_binding(
    client: OrchestratorChromeClient,
    page: OrchestratorMcpPage,
    url: str,
    *,
    daemon: BrowserOrchestratorClient,
    session_id: str,
) -> None:
    """Seed window.name then navigate so e2e-runtime-bootstrap.js binds private API."""
    api_base = get_open_page_api_url().rstrip("/")
    if not api_base or api_base == "http://127.0.0.1:8080":
        daemon.navigate_page(session_id, page.target_id, url)
        page.url = url
        return
    if not wait_e2e_provider_ready(api_url=api_base, timeout_sec=60.0):
        raise RuntimeError(
            f"E2E_RUNTIME_BINDING_FAILED: private API not ready before binding: {api_base}"
        )
    source = e2e_runtime_binding_source()
    if source:
        client.evaluate(
            page,
            f"(() => {{{source} return true; }})()",
            timeout_sec=15.0,
        )
    else:
        client.evaluate(
            page,
            e2e_api_base_inject_js(api_base),
            timeout_sec=15.0,
        )
    daemon.navigate_page(session_id, page.target_id, url)
    page.url = url


@contextmanager
def open_orchestrator_mcp_page(
    url: str,
    *,
    request_timeout_sec: float = 180.0,
) -> Iterator[tuple[OrchestratorChromeClient, OrchestratorMcpPage]]:
    daemon = BrowserOrchestratorClient(timeout_sec=max(request_timeout_sec, 90.0))
    wait_wall = float(os.environ.get("MYRM_BROWSER_ORCHESTRATOR_WAIT_SEC", "90"))
    _wait_orchestrator_daemon_ready(daemon, wall_sec=max(20.0, wait_wall))
    session_id = _resolve_session_id()
    daemon.create_session(session_id)
    page = OrchestratorMcpPage(page_id=1, target_id="", url=None)
    client = OrchestratorChromeClient(
        session_id=session_id,
        daemon=daemon,
        request_timeout_sec=request_timeout_sec,
    )
    try:
        binding_source = e2e_runtime_binding_source()
        if binding_source:
            binding_expression = f"(() => {{{binding_source} return true; }})()"
            created = daemon.open_page_transaction(
                session_id,
                url=url,
                binding_expression=binding_expression,
            )
        else:
            api_base = get_open_page_api_url().rstrip("/")
            if api_base and api_base != "http://127.0.0.1:8080":
                if not wait_e2e_provider_ready(api_url=api_base, timeout_sec=60.0):
                    raise RuntimeError(
                        f"E2E_RUNTIME_BINDING_FAILED: private API not ready: {api_base}"
                    )
                inject = e2e_api_base_inject_js(api_base)
                created = daemon.open_page_transaction(
                    session_id,
                    url=url,
                    binding_expression=f"(() => {{{inject} return true; }})()",
                )
            else:
                created = daemon.open_page_transaction(session_id, url=url)
        page.page_id = int(created["pageId"])
        page.target_id = str(created["targetId"])
        page.url = str(created.get("url", url))
        try:
            from chrome_e2e.gates.orphan_budget import assert_orphan_budget_invariant  # noqa: PLC0415

            assert_orphan_budget_invariant()
        except ImportError:
            pass
        yield client, page
    finally:
        daemon.destroy_session(session_id)
