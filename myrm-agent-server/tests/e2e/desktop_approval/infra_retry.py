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
    if "detached frame" in message:
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
    if isinstance(exc, ExceptionGroup):
        return any(is_retriable_page_transport(sub) for sub in exc.exceptions)
    return False


async def heal_chrome_attach_before_reopen() -> None:
    """R46 attach heal before mux page reopen (orchestrator-owned, not user cleanup)."""
    progress("chrome attach heal before page reopen")
    await asyncio.to_thread(assert_chrome_attach_health)


async def open_mcp_chat_page(client: ChromeMcpClient) -> McpPage:
    """Open chat UI; prefer about:blank (no runtime binding), then recover, then direct :3000."""
    last_exc: BaseException | None = None
    strategies: list[tuple[str, str]] = [
        ("about_blank", "about:blank"),
        ("about_blank_recover", "about:blank"),
        ("direct", BASE_URL),
    ]
    for attempt, (mode, url) in enumerate(strategies, start=1):
        heartbeat_e2e_lease()
        try:
            if mode.endswith("_recover"):
                progress(f"mux recover before new_page attempt {attempt}/3")
                await heal_chrome_attach_before_reopen()
                await asyncio.to_thread(client.recover_mux_transport)
            if url == "about:blank":
                progress(f"new_page about:blank attempt {attempt}/3")
                page = await asyncio.to_thread(
                    client.new_page,
                    "about:blank",
                    timeout_ms=90_000,
                )
                progress("navigate to chat UI")
                chat_home = f"{BASE_URL.rstrip('/')}/"
                for nav_pass in (1, 2):
                    await asyncio.to_thread(
                        client.navigate,
                        page,
                        chat_home,
                        timeout_ms=120_000,
                    )
                    await asyncio.sleep(2.0)
                    probe = await asyncio.to_thread(
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
                        await asyncio.to_thread(
                            client.reload,
                            page,
                            timeout_ms=120_000,
                        )
                        await asyncio.sleep(3.0)
                        probe = await asyncio.to_thread(
                            client.evaluate,
                            page,
                            """(() => ({
                              path: location.pathname || 'blank',
                              hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
                            }))()""",
                            timeout_sec=30.0,
                        )
                        if isinstance(probe, dict) and probe.get("hasLayout"):
                            return page
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
            progress(f"new_page {url} attempt {attempt}/3 (direct fallback)")
            page = await asyncio.to_thread(
                client.new_page,
                url,
                timeout_ms=120_000,
            )
            probe = await asyncio.to_thread(
                client.evaluate,
                page,
                """(() => ({
                  path: location.pathname || 'blank',
                  hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
                }))()""",
                timeout_sec=30.0,
            )
            if isinstance(probe, dict) and probe.get("hasLayout"):
                return page
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
            progress(f"open/nav mux retry {attempt}/3 after: {exc}")
            await asyncio.to_thread(client.recover_mux_transport)
            await asyncio.sleep(5.0 * attempt)
    raise last_exc or RuntimeError("Chrome MCP open/nav failed without exception")
