"""Chrome MCP orchestration for desktop control approval E2E.

[INPUT]
- cdp_chat_support::wait_e2e_provider_ready (POS: live E2E API readiness probe)
- mcp_chat_ui::McpChatSession (POS: chat UI automation over MCP)
- tests.e2e.desktop_approval.* (POS: desktop approval E2E helper modules)

[OUTPUT]
- run_desktop_approval_chrome_e2e: full allow-once / allow-always→revoke runner
- retry: assert_chrome_attach_health → mux recover → page reopen on retriable transport errors

[POS]
Top-level Chrome E2E entry for desktop trust flows; owns MCP client lifecycle and retries.
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable

import pytest
from cdp_chat.support import (
    ensure_e2e_hitl_mode,
    ensure_e2e_hitl_mode_in_browser,
    fetch_provider_readiness_snapshot,
    get_e2e_api_url,
    signoff_parallel_desktop_mux_step_timeout_sec,
    wait_e2e_provider_ready,
)
from cdp_chat.mcp_ui import McpChatSession

from tests.e2e.desktop_approval.constants import BASE_URL, max_send_attempts, progress
from tests.e2e.desktop_approval.infra_retry import (
    heal_chrome_attach_before_reopen,
    is_retriable_page_transport,
    should_abort_desktop_e2e_retries,
)
from tests.e2e.desktop_approval.textedit_fixture import hide_textedit_fixture
from tests.e2e.desktop_approval.trust_api import (
    clear_persisted_desktop_approvals,
    desktop_accessibility_granted,
)
from tests.e2e.desktop_approval.turn_flow import run_approval_attempt
from tests.support.chrome_mcp_e2e import OpenMcpPageSession, open_mcp_page_async
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once


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
        ensure_e2e_hitl_mode(api_url=get_e2e_api_url())
        await ensure_e2e_hitl_mode_in_browser(chat)

        async def _retry_reset_step(
            label: str,
            awaitable: Awaitable[object],
            *,
            timeout_sec: float,
        ) -> object:
            try:
                return await asyncio.wait_for(awaitable, timeout=timeout_sec)
            except asyncio.TimeoutError as exc:
                await asyncio.to_thread(chat._client.abandon_inflight_requests)
                raise TimeoutError(
                    "retry reset evaluate wall-timeout "
                    f"step={label} timeout={timeout_sec:.0f}s"
                ) from exc

        last_error: dict[str, object] | None = None
        attempts = max_send_attempts(scope)
        for attempt in range(1, attempts + 1):
            heartbeat_once()
            progress(f"{label} attempt {attempt}/{attempts}")
            ensure_e2e_hitl_mode(api_url=get_e2e_api_url())
            clear_persisted_desktop_approvals()
            try:
                chat_id = await run_approval_attempt(chat, scope=scope)
                e2e_resource_ledger.register("chat", chat_id)
                return chat_id
            except (AssertionError, RuntimeError, TimeoutError, OSError) as exc:
                last_error = {
                    "attempt": attempt,
                    "error": str(exc),
                    "type": type(exc).__name__,
                }
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
                    from e2e_session_runtime.lifecycle import remaining_wall_sec

                    body_remaining = remaining_wall_sec()
                except ImportError:
                    body_remaining = float("inf")
                retry_body_reserve = signoff_parallel_desktop_mux_step_timeout_sec(
                    180.0
                )
                if body_remaining < retry_body_reserve:
                    progress(
                        "R255 skip internal retry — body budget remaining "
                        f"{body_remaining:.0f}s < reserve {retry_body_reserve:.0f}s"
                    )
                    break
                if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
                    from tests.e2e.desktop_approval.turn_flow import (
                        _signoff_mux_recover_lightweight,
                    )

                    progress("R288 signoff skip recover_mux_transport on allow-once retry")
                    await _signoff_mux_recover_lightweight(
                        chat,
                        reason="signoff desktop allow-once internal retry",
                    )
                else:
                    await _retry_reset_step(
                        "recover_mux_transport",
                        asyncio.to_thread(chat._client.recover_mux_transport),
                        timeout_sec=40.0,
                    )
                try:
                    progress("retry reset: lightweight chat reset (no page reopen)")
                    mux_step_timeout = signoff_parallel_desktop_mux_step_timeout_sec(
                        75.0
                    )
                    await asyncio.sleep(1.0)
                    progress("new chat + ensure surface")
                    chat._reset_shell_session_clock()
                    await _retry_reset_step(
                        "ensure_chat_surface/pre",
                        chat.ensure_chat_surface(BASE_URL, timeout_sec=90.0),
                        timeout_sec=mux_step_timeout,
                    )
                    await _retry_reset_step(
                        "ensure_react_e2e_bridge/pre",
                        chat.ensure_react_e2e_bridge(timeout_sec=90.0),
                        timeout_sec=mux_step_timeout,
                    )
                    await _retry_reset_step(
                        "click_new_chat",
                        chat.click_new_chat(timeout_sec=mux_step_timeout),
                        timeout_sec=mux_step_timeout,
                    )
                    await _retry_reset_step(
                        "ensure_chat_surface/post",
                        chat.ensure_chat_surface(BASE_URL, timeout_sec=90.0),
                        timeout_sec=mux_step_timeout,
                    )
                    await _retry_reset_step(
                        "ensure_react_e2e_bridge/post",
                        chat.ensure_react_e2e_bridge(timeout_sec=90.0),
                        timeout_sec=mux_step_timeout,
                    )
                except (RuntimeError, TimeoutError, OSError) as reset_exc:
                    if is_retriable_page_transport(reset_exc):
                        progress(
                            f"page transport error during retry reset: {reset_exc}"
                        )
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

    async def _open_chat_page() -> OpenMcpPageSession:
        request_timeout_sec = 180.0
        if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
            from dev_gate.contract import signoff_open_mcp_budgets

            from tests.support.chrome_mcp_e2e import _parallel_open_page_peer_count

            budgets = signoff_open_mcp_budgets(
                parallel_peers=_parallel_open_page_peer_count(),
            )
            request_timeout_sec = min(180.0, budgets.total_budget_sec + 30.0)
        progress("open chat page (open_mcp_page SSOT)")
        return await open_mcp_page_async(
            BASE_URL.rstrip("/"),
            timeout_ms=90_000,
            request_timeout_sec=request_timeout_sec,
        )

    page_session = await _open_chat_page()
    try:
        try:
            chat = McpChatSession(page_session.client, page_session.page)
        except (TimeoutError, RuntimeError) as open_exc:
            if not is_retriable_page_transport(open_exc):
                raise
            progress(f"reopen chat page after open exhaustion: {open_exc}")
            await page_session.aclose()
            await heal_chrome_attach_before_reopen()
            page_session = await _open_chat_page()
            chat = McpChatSession(page_session.client, page_session.page)
        progress("run approval flow")
        try:
            await run_flow(chat)
        except (RuntimeError, TimeoutError, OSError) as exc:
            if not is_retriable_page_transport(exc):
                raise
            progress(
                f"attach heal + mux recover + reopen after page transport error: {exc}"
            )
            await heal_chrome_attach_before_reopen()
            if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
                from tests.e2e.desktop_approval.turn_flow import (
                    _signoff_mux_recover_lightweight,
                )

                progress("R288 signoff skip recover_mux_transport on page transport heal")
                await _signoff_mux_recover_lightweight(
                    chat,
                    reason="signoff desktop page transport heal reopen",
                )
            else:
                await asyncio.to_thread(page_session.client.recover_mux_transport)
            await asyncio.sleep(2.0)
            await page_session.aclose()
            page_session = await _open_chat_page()
            chat = McpChatSession(page_session.client, page_session.page)
            await run_flow(chat)
    finally:
        try:
            await page_session.aclose()
        except BaseException as exc:
            if not should_abort_desktop_e2e_retries(exc):
                raise
            progress(f"Chrome MCP cleanup skipped after infra failure: {exc}")
        await asyncio.to_thread(hide_textedit_fixture)
