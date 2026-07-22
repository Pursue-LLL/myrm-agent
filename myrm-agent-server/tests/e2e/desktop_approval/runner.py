"""Chrome MCP orchestration for desktop control approval E2E.

[INPUT]
- cdp_chat_support::wait_e2e_provider_ready (POS: live E2E API readiness probe)
- chrome_mcp_client::ChromeMcpClient (POS: synchronous Chrome MCP mux client)
- mcp_chat_ui::McpChatSession (POS: chat UI automation over MCP)
- tests.e2e.desktop_approval.* (POS: desktop approval E2E helper modules)

[OUTPUT]
- run_desktop_approval_chrome_e2e: full allow-once / allow-always→revoke runner
- mux recover + page reopen on retriable page transport errors

[POS]
Top-level Chrome E2E entry for desktop trust flows; owns MCP client lifecycle and retries.
"""

from __future__ import annotations

import asyncio

import pytest
from cdp_chat_support import fetch_provider_readiness_snapshot, get_e2e_api_url, wait_e2e_provider_ready
from chrome_mcp_client import ChromeMcpClient
from mcp_chat_ui import McpChatSession

from tests.e2e.desktop_approval.constants import BASE_URL, max_send_attempts, progress
from tests.e2e.desktop_approval.infra_retry import (
    is_retriable_page_transport,
    open_mcp_chat_page,
    should_abort_desktop_e2e_retries,
)
from tests.e2e.desktop_approval.textedit_fixture import hide_textedit_fixture
from tests.e2e.desktop_approval.trust_api import clear_persisted_desktop_approvals, desktop_accessibility_granted
from tests.e2e.desktop_approval.turn_flow import run_approval_attempt
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease


async def run_desktop_approval_chrome_e2e(
    *,
    scope: str,
    label: str,
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready(timeout_sec=180.0, poll_interval_sec=2.0):
        readiness = fetch_provider_readiness_snapshot()
        pytest.fail(
            "Provider config not ready for live E2E — run via ./myrm test -m chrome_e2e "
            f"after ./myrm ready --chrome (readiness={readiness})"
        )
    if not desktop_accessibility_granted():
        pytest.fail(
            "macOS Accessibility permission is not granted for the backend — "
            "open System Settings → Privacy & Security → Accessibility and allow Cursor/Terminal, "
            "then retry after ./myrm restart --chrome"
        )

    progress("clear persisted desktop approvals")
    clear_persisted_desktop_approvals()

    async def run_flow(chat: McpChatSession) -> str:
        await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=120.0)

        last_error: dict[str, object] | None = None
        attempts = max_send_attempts(scope)
        for attempt in range(1, attempts + 1):
            heartbeat_e2e_lease()
            progress(f"{label} attempt {attempt}/{attempts}")
            clear_persisted_desktop_approvals()
            try:
                chat_id = await run_approval_attempt(chat, scope=scope)
                e2e_resource_ledger.register("chat", chat_id)
                return chat_id
            except (AssertionError, RuntimeError, TimeoutError, OSError) as exc:
                last_error = {"attempt": attempt, "error": str(exc), "type": type(exc).__name__}
                if is_retriable_page_transport(exc):
                    progress(f"page transport error during attempt: {last_error}")
                    raise
                if should_abort_desktop_e2e_retries(exc):
                    pytest.fail(
                        "Desktop approval Chrome E2E hit non-retriable infra failure "
                        f"(api={get_e2e_api_url()}): {last_error}. "
                        "Parallel tests should queue via E2E_LEASE_WAIT; "
                        "orchestrator heal (wave/mux) is required — not user cleanup."
                    )
                if attempt >= attempts:
                    break
                progress(f"retry after: {last_error}")
                try:
                    await asyncio.to_thread(
                        chat._client.navigate,
                        chat._page,
                        f"{BASE_URL.rstrip('/')}/",
                        timeout_ms=120_000,
                    )
                    await asyncio.sleep(2.0)
                    await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=120.0)
                    progress("new chat + ensure surface")
                    await chat.click_new_chat()
                    await chat.ensure_chat_surface(BASE_URL)
                except (RuntimeError, TimeoutError, OSError) as reset_exc:
                    if is_retriable_page_transport(reset_exc):
                        progress(f"page transport error during retry reset: {reset_exc}")
                        raise reset_exc from exc
                    if should_abort_desktop_e2e_retries(reset_exc):
                        pytest.fail(
                            "Desktop approval Chrome E2E lost UI bridge during retry "
                            f"(api={get_e2e_api_url()}): {last_error}; reset={reset_exc}"
                        )
                await asyncio.sleep(2.0)

        pytest.fail(
            f"Desktop approval Chrome E2E ({label}) failed after {attempts} attempts "
            f"(api={get_e2e_api_url()}): {last_error}"
        )

    client = ChromeMcpClient(request_timeout_sec=180.0)
    progress("start chrome MCP client")
    await asyncio.to_thread(client.start)
    try:
        page = await open_mcp_chat_page(client)
        chat = McpChatSession(client, page)
        progress("run approval flow")
        try:
            await run_flow(chat)
        except (RuntimeError, TimeoutError, OSError) as exc:
            if not is_retriable_page_transport(exc):
                raise
            progress(f"mux recover + reopen after page transport error: {exc}")
            await asyncio.to_thread(client.recover_mux_transport)
            await asyncio.sleep(2.0)
            page = await open_mcp_chat_page(client)
            chat = McpChatSession(client, page)
            await run_flow(chat)
    finally:
        try:
            client.close()
        except BaseException as exc:
            if not should_abort_desktop_e2e_retries(exc):
                raise
            progress(f"Chrome MCP cleanup skipped after infra failure: {exc}")
        await asyncio.to_thread(hide_textedit_fixture)
