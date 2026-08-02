"""Infra retry helpers for desktop approval Chrome E2E.

[OUTPUT]
- heal_chrome_attach_before_reopen
- should_abort_desktop_e2e_retries, is_retriable_page_transport

[POS]
Transport error classification + attach heal only. Page open SSOT: open_mcp_page / open_mcp_page_async.
"""

from __future__ import annotations

import asyncio
import os

from tests.e2e.desktop_approval.constants import INFRA_ABORT_MARKERS, progress
from tests.support.e2e_runtime_guard import assert_chrome_attach_health


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


def is_retriable_page_transport(exc: BaseException) -> bool:
    """Mux timeout or detached CDP frame — orchestrator should recover + reopen page."""
    message = str(exc).lower()
    if isinstance(exc, TimeoutError):
        return any(
            token in message
            for token in (
                "new_page",
                "navigate",
                "reload",
                "evaluate",
                "detached frame",
                "not owned by this shim session",
                "no mcpage found for the given page",
                "chrome mcp transport closed",
                "open_mcp_page",
            )
        )
    if "detached frame" in message:
        return True
    if "no page found" in message:
        return True
    if "not owned by this shim session" in message:
        return True
    if "no mcpage found for the given page" in message:
        return True
    if is_mux_new_page_retriable(exc):
        return True
    if "chrome mcp transport closed" in message:
        return True
    if "chrome mcp client is not running" in message:
        return True
    if "not running after transport" in message:
        return True
    if "dev e2e chat bridge not available" in message:
        return True
    if "connection reset during tools/call" in message:
        return True
    if "mux_reclaim_stall" in message:
        return True
    if "thread join timed out" in message:
        return True
    if "request lock wall budget exhausted" in message:
        return True
    if isinstance(exc, ExceptionGroup):
        return any(is_retriable_page_transport(sub) for sub in exc.exceptions)
    return False


async def heal_chrome_attach_before_reopen() -> None:
    """R46 attach heal before mux page reopen (orchestrator-owned, not user cleanup)."""
    if (
        os.environ.get("E2E_SIGNOFF", "").strip() == "1"
        and os.environ.get("MYRM_E2E_BOOT_MUX_GATE_OK", "").strip() == "1"
    ):
        progress("chrome attach heal skipped (boot mux gate ok)")
        return
    progress("chrome attach heal before page reopen")
    await asyncio.to_thread(assert_chrome_attach_health)
