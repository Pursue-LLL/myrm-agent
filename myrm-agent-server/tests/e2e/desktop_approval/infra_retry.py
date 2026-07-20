"""Infra retry helpers for desktop approval Chrome E2E.

[INPUT]
- chrome_mcp_client::ChromeMcpClient (POS: synchronous Chrome MCP mux client)
- tests.e2e.desktop_approval.constants (POS: desktop approval E2E tuning knobs)
- tests.support.e2e_runtime_guard::heartbeat_e2e_lease (POS: live E2E lease heartbeat)

[OUTPUT]
- ensure_mux_stack_ready, open_mcp_chat_page, should_abort_desktop_e2e_retries

[POS]
Mux/page-open retry layer for desktop approval Chrome E2E; orchestrator-owned heal, not user cleanup.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from chrome_mcp_client import ChromeMcpClient, McpPage

from tests.e2e.desktop_approval.constants import BASE_URL, INFRA_ABORT_MARKERS, progress
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease

_REPO_ROOT = Path(__file__).resolve().parents[5]
_MYRM_BIN = _REPO_ROOT / "myrm"


def ensure_mux_stack_ready() -> None:
    """Re-run attach preflight so mux timeout drift can self-heal before opening pages."""
    if not _MYRM_BIN.is_file():
        progress("mux attach heal skipped: myrm launcher missing")
        return
    env = os.environ.copy()
    env.setdefault("MYRM_MUX_ALLOW_TIMEOUT_RESTART", "1")
    progress("mux attach heal via ./myrm ready --attach --chrome")
    result = subprocess.run(
        [str(_MYRM_BIN), "ready", "--attach", "--chrome"],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    if result.returncode != 0:
        progress(f"mux attach heal failed (exit={result.returncode}): {combined[-400:]}")
        return
    if "restarting owned mux namespace" in combined:
        progress("mux attach heal restarted daemon")
    else:
        progress("mux attach heal ok")


def should_abort_desktop_e2e_retries(exc: BaseException) -> bool:
    message = str(exc)
    if any(marker in message for marker in INFRA_ABORT_MARKERS):
        return True
    if isinstance(exc, ExceptionGroup):
        return any(should_abort_desktop_e2e_retries(sub) for sub in exc.exceptions)
    return False


def is_mux_new_page_retriable(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        "upstream request timed out" in message
        or ("tools/call error" in message and "timed out" in message)
        or "transient_mux" in message
    )


async def open_mcp_chat_page(client: ChromeMcpClient) -> McpPage:
    """Open chat UI without runtime-binding new_page (avoids attach navigate hang)."""
    last_exc: BaseException | None = None
    for attempt in range(1, 4):
        heartbeat_e2e_lease()
        use_direct_ui = attempt >= 3
        try:
            if use_direct_ui:
                progress(f"new_page {BASE_URL} attempt {attempt}/3 (direct UI fallback)")
                page = await asyncio.to_thread(
                    client.new_page,
                    BASE_URL,
                    timeout_ms=120_000,
                )
                return page
            progress(f"new_page about:blank attempt {attempt}/3")
            page = await asyncio.to_thread(
                client.new_page,
                "about:blank",
                timeout_ms=90_000,
            )
            progress("navigate to chat UI")
            await asyncio.to_thread(
                client.navigate,
                page,
                BASE_URL,
                timeout_ms=120_000,
            )
            return page
        except (TimeoutError, RuntimeError) as exc:
            last_exc = exc
            if should_abort_desktop_e2e_retries(exc) and not is_mux_new_page_retriable(exc):
                raise
            if attempt >= 3 or not is_mux_new_page_retriable(exc):
                raise
            progress(f"open/nav mux retry {attempt}/3 after: {exc}")
            await asyncio.to_thread(client.recover_mux_transport)
            if attempt >= 2:
                await asyncio.to_thread(ensure_mux_stack_ready)
            await asyncio.sleep(5.0 * attempt)
    raise last_exc or RuntimeError("Chrome MCP open/nav failed without exception")
