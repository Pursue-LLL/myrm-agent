"""A real-Chromium session in a context whose domain allowlist holds only the loopback host.

[INPUT]
- browser::BrowserSession, DomainAllowlist (POS: the session under test and the allowlist its context is given)
- browser.pool::GlobalBrowserPool, BrowserPoolConfig, ContextType (POS: the pooled context production creates)
- browser.utils.private_origins::private_origin_grants (POS: the explicit private origins local mode may navigate to)
- tests.toolkits.browser._redirect_servers::Site (POS: the loopback server the session is allowed to reach)

[OUTPUT]
- allowlisted_session: async context manager yielding a ``BrowserSession`` with one open tab, shut down on exit

[POS]
Shared by the integration tests that prove the allowlist holds for the page's scripts and for the agent's own
JavaScript. The session is built the way production builds it (pool, ``ContextType.AGENT``, domain allowlist,
``allow_private_networks``), so a policy that only works on a hand-built context cannot pass.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from myrm_agent_harness.toolkits.browser import BrowserSession, DomainAllowlist
from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.utils.private_origins import private_origin_grants
from tests.toolkits.browser._redirect_servers import Site


@asynccontextmanager
async def allowlisted_session(site: Site) -> AsyncIterator[BrowserSession]:
    """A session in a pooled context that allows ``127.0.0.1`` only; ``site`` is the server it may navigate to."""
    pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal())
    session = BrowserSession(
        pool,
        ContextType.AGENT,
        domain_allowlist=DomainAllowlist.from_strings(("127.0.0.1",)),
        allow_private_networks=True,
    )
    try:
        await session.new_tab()
        context = session.get_active_page().context
        private_origin_grants(context).grant(site.base_url)
        # Chromium's Local Network Access would stop one loopback server from reaching another whatever the allowlist
        # says, which would hide a connection the policy failed to refuse.
        await context.grant_permissions(["local-network-access"])
        yield session
    finally:
        await session.close()
        await pool.shutdown()
