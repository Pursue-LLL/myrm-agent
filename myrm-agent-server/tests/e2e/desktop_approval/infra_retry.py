"""Infra retry helpers for desktop approval Chrome E2E."""

from __future__ import annotations

import asyncio

from chrome_mcp_client import ChromeMcpClient, McpPage

from tests.e2e.desktop_approval.constants import BASE_URL, INFRA_ABORT_MARKERS, progress
from tests.support.e2e_runtime_guard import heartbeat_e2e_lease


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
        try:
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
            await asyncio.sleep(5.0 * attempt)
    raise last_exc or RuntimeError("Chrome MCP open/nav failed without exception")
