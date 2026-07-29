"""Infra retry helpers for desktop approval Chrome E2E.

[INPUT]
- chrome_mcp_client::ChromeMcpClient (POS: synchronous Chrome MCP mux client)
- tests.e2e.desktop_approval.constants (POS: desktop approval E2E tuning knobs)
- tests.support.e2e_runtime_guard::assert_chrome_attach_health (POS: Chrome mux/CDP attach gate)
- tests.support.e2e_runtime_guard::heartbeat_e2e_lease (POS: live E2E lease heartbeat)

[OUTPUT]
- heal_chrome_attach_before_reopen, open_mcp_chat_page
- should_abort_desktop_e2e_retries, is_mux_new_page_retriable, is_retriable_page_transport

[POS]
Mux/page-open retry layer for desktop approval Chrome E2E; orchestrator-owned heal, not user cleanup.
"""

from __future__ import annotations

import asyncio
import os

from chrome_mcp_client import ChromeMcpClient, McpPage

from tests.e2e.desktop_approval.constants import BASE_URL, INFRA_ABORT_MARKERS, progress
from tests.support.e2e_runtime_guard import (
    assert_chrome_attach_health,
    heartbeat_e2e_lease,
)


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
        # Do not treat generic API/socket timeout as page transport. Only retry here
        # when timeout text clearly points to CDP page open/nav/eval/reload paths.
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
    if "dev e2e chat bridge not available" in message:
        return True
    if "connection reset during tools/call" in message:
        return True
    if isinstance(exc, ExceptionGroup):
        return any(is_retriable_page_transport(sub) for sub in exc.exceptions)
    return False


async def heal_chrome_attach_before_reopen() -> None:
    """R46 attach heal before mux page reopen (orchestrator-owned, not user cleanup)."""
    progress("chrome attach heal before page reopen")
    await asyncio.to_thread(assert_chrome_attach_health)


def _resolve_open_nav_wall_timeout_sec() -> float:
    """R81/R85: signoff desktop leg queues on mux cold attach under parallel chrome_e2e."""
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        from dev_gate_contract import SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC

        return float(SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC)
    return 70.0


def _resolve_open_nav_strategies() -> list[tuple[str, str]]:
    """R86/R88/R91: signoff direct-only with mux-recover retries (no about:blank burn)."""
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        from dev_gate_contract import SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT

        count = max(1, SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT)
        strategies: list[tuple[str, str]] = [("direct", BASE_URL)]
        strategies.extend(("direct_recover", BASE_URL) for _ in range(count - 1))
        return strategies
    return [
        ("about_blank", "about:blank"),
        ("about_blank_recover", "about:blank"),
        ("direct", BASE_URL),
    ]


def _is_signoff_open_nav() -> bool:
    return os.environ.get("E2E_SIGNOFF", "").strip() == "1"


def _finalize_open_nav_page(page: McpPage) -> McpPage:
    """R88: signoff open/nav reserve is pre-body; reset BODY wall for test proper."""
    if _is_signoff_open_nav():
        from e2e_session_lifecycle import begin_body_wall_budget

        progress("signoff body wall reset after open/nav")
        begin_body_wall_budget(phase_label="desktop_post_open")
    return page


async def open_mcp_chat_page(client: ChromeMcpClient) -> McpPage:
    """Open chat UI; prefer about:blank (no runtime binding), then recover, then direct :3000."""
    last_exc: BaseException | None = None
    open_nav_wall = _resolve_open_nav_wall_timeout_sec()
    eval_wall_timeout_sec = 45.0

    async def _call_with_wall_timeout(
        label: str,
        wall_timeout_sec: float,
        fn: object,
        *args: object,
        **kwargs: object,
    ) -> object:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(fn, *args, **kwargs),
                timeout=wall_timeout_sec,
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"{label} wall timeout after {wall_timeout_sec:.0f}s"
            ) from exc

    strategies: list[tuple[str, str]] = _resolve_open_nav_strategies()
    strategy_count = len(strategies)
    for attempt, (mode, url) in enumerate(strategies, start=1):
        heartbeat_e2e_lease()
        new_page_wall_timeout_sec = open_nav_wall
        navigate_wall_timeout_sec = open_nav_wall
        reload_wall_timeout_sec = open_nav_wall
        try:
            if mode.endswith("_recover"):
                progress(f"mux recover before new_page attempt {attempt}/{strategy_count}")
                await heal_chrome_attach_before_reopen()
                await asyncio.to_thread(client.recover_mux_transport)
            if url == "about:blank":
                progress(f"new_page about:blank attempt {attempt}/{strategy_count}")
                page = await _call_with_wall_timeout(
                    "new_page about:blank",
                    new_page_wall_timeout_sec,
                    client.new_page,
                    "about:blank",
                    timeout_ms=90_000,
                )
                progress("navigate to chat UI")
                chat_home = f"{BASE_URL.rstrip('/')}/"
                for nav_pass in (1, 2):
                    await _call_with_wall_timeout(
                        "navigate chat home",
                        navigate_wall_timeout_sec,
                        client.navigate,
                        page,
                        chat_home,
                        timeout_ms=120_000,
                    )
                    await asyncio.sleep(2.0)
                    probe = await _call_with_wall_timeout(
                        "evaluate post-navigate layout",
                        eval_wall_timeout_sec,
                        client.evaluate,
                        page,
                        """(() => ({
                          path: location.pathname || 'blank',
                          hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
                        }))()""",
                        timeout_sec=30.0,
                    )
                    if isinstance(probe, dict) and probe.get("hasLayout"):
                        progress("post-navigate reload for fresh dev bridge bundle")
                        await _call_with_wall_timeout(
                            "reload chat page",
                            reload_wall_timeout_sec,
                            client.reload,
                            page,
                            timeout_ms=120_000,
                        )
                        await asyncio.sleep(3.0)
                        probe = await _call_with_wall_timeout(
                            "evaluate post-reload layout",
                            eval_wall_timeout_sec,
                            client.evaluate,
                            page,
                            """(() => ({
                              path: location.pathname || 'blank',
                              hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
                            }))()""",
                            timeout_sec=30.0,
                        )
                        if isinstance(probe, dict) and probe.get("hasLayout"):
                            return _finalize_open_nav_page(page)
                        if nav_pass == 1:
                            progress(
                                "post-reload layout retry "
                                f"(path={probe.get('path') if isinstance(probe, dict) else probe})"
                            )
                            continue
                        break
                    if nav_pass == 1:
                        progress(
                            "navigate verify retry "
                            f"(path={probe.get('path') if isinstance(probe, dict) else probe})"
                        )
                progress(
                    "about:blank navigate verify failed "
                    f"(path={probe.get('path') if isinstance(probe, dict) else probe}); next strategy"
                )
                continue
            progress(f"new_page {url} attempt {attempt}/{strategy_count} (direct fallback)")
            page = await _call_with_wall_timeout(
                f"new_page {url}",
                new_page_wall_timeout_sec,
                client.new_page,
                url,
                timeout_ms=120_000,
            )
            probe = await _call_with_wall_timeout(
                "evaluate direct layout",
                eval_wall_timeout_sec,
                client.evaluate,
                page,
                """(() => ({
                  path: location.pathname || 'blank',
                  hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
                }))()""",
                timeout_sec=30.0,
            )
            if isinstance(probe, dict) and probe.get("hasLayout"):
                return _finalize_open_nav_page(page)
            progress(
                "direct new_page layout missing "
                f"(path={probe.get('path') if isinstance(probe, dict) else probe})"
            )
            continue
        except (TimeoutError, RuntimeError) as exc:
            last_exc = exc
            if should_abort_desktop_e2e_retries(
                exc
            ) and not is_retriable_page_transport(exc):
                raise
            if attempt >= len(strategies) or not is_retriable_page_transport(exc):
                raise
            progress(f"open/nav mux retry {attempt}/{strategy_count} after: {exc}")
            if isinstance(exc, TimeoutError):
                progress("open/nav wall timeout — abandon in-flight mux requests")
                await asyncio.to_thread(client.abandon_inflight_requests)
            await asyncio.to_thread(client.recover_mux_transport)
            await asyncio.sleep(5.0 * attempt)
    raise last_exc or RuntimeError("Chrome MCP open/nav failed without exception")
