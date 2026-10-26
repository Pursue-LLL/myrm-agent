"""A real-Chromium BrowserSession that may reach loopback fixtures, for browser integration tests.

[INPUT]
- toolkits.browser::BrowserSession (POS: the aggregate root every browser tool talks to)
- toolkits.browser.pool::GlobalBrowserPool, ContextType (POS: browser process pool; the context kind a session runs in)

[OUTPUT]
- local_session: async context manager yielding a session with one open tab, closed together with its pool on exit

[POS]
Test support: ``allow_private_networks=True`` is what lets the session navigate to a loopback server (see
``_redirect_servers``) while every other private origin stays blocked, so a test exercises the real policy rather than a
patched one. Tests that need other launch options or a different context kind build their own session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool


@asynccontextmanager
async def local_session() -> AsyncIterator[BrowserSession]:
    pool = GlobalBrowserPool(max_browsers=1)
    session = BrowserSession(pool, ContextType.AGENT, allow_private_networks=True)
    try:
        await session.new_tab()
        yield session
    finally:
        await session.close()
        await pool.shutdown()
