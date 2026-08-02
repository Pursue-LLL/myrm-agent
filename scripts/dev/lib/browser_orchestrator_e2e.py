"""E2E page lifecycle via Browser Orchestrator daemon (P0-B fail-closed path).

Used when ``MYRM_BROWSER_ORCHESTRATOR=1`` — no mux MCP fallback.
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from browser_orchestrator_client import BrowserOrchestratorClient


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
        _ = timeout_sec
        payload = self._daemon.evaluate_page(
            self._session_id,
            page.target_id,
            expression,
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


def _resolve_session_id() -> str:
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    if run_id:
        return run_id
    return f"orchestrator-e2e-{os.getpid()}-{uuid.uuid4().hex[:8]}"


@contextmanager
def open_orchestrator_mcp_page(
    url: str,
    *,
    request_timeout_sec: float = 180.0,
) -> Iterator[tuple[OrchestratorChromeClient, OrchestratorMcpPage]]:
    daemon = BrowserOrchestratorClient()
    deadline = time.monotonic() + 20.0
    while not daemon.is_alive():
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "BROWSER_ORCHESTRATOR_REQUIRED: daemon not running — "
                "run MYRM_BROWSER_ORCHESTRATOR=1 ./myrm ready --chrome"
            )
        time.sleep(0.5)
    session_id = _resolve_session_id()
    daemon.create_session(session_id)
    page = OrchestratorMcpPage(page_id=1, target_id="", url=None)
    client = OrchestratorChromeClient(
        session_id=session_id,
        daemon=daemon,
        request_timeout_sec=request_timeout_sec,
    )
    try:
        created = daemon.create_page(session_id, url)
        page.target_id = str(created["targetId"])
        page.url = url
        yield client, page
    finally:
        daemon.destroy_session(session_id)
