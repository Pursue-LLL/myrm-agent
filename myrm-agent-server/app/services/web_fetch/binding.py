"""Per agent-run binding of WFEL providers into harness CrawlEngine.

[INPUT]
- myrm_agent_harness.toolkits.web_fetch.escalation.context::bind_web_fetch_escalation_context (POS: Escalation context binding)
- app.services.web_fetch.escalation.registry::build_escalation_providers (POS: Provider chain builder)

[OUTPUT]
- open_web_fetch_escalation_context: Async context manager binding WFEL providers for an agent run.
- resolve_browser_launch_mode: Map browser_source string to LaunchMode enum.

[POS]
Per agent-run binding of web fetch escalation providers into harness CrawlEngine.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from myrm_agent_harness.toolkits.browser.pool.config import LaunchMode
from myrm_agent_harness.toolkits.web_fetch.escalation.context import bind_web_fetch_escalation_context

from app.services.web_fetch.escalation.registry import build_escalation_providers

logger = logging.getLogger(__name__)


def resolve_browser_launch_mode(browser_source: str | None) -> LaunchMode | None:
    if not browser_source:
        return None
    normalized = browser_source.strip().lower()
    try:
        return LaunchMode(normalized)
    except ValueError:
        logger.debug("Unknown browser_source for web_fetch L2: %s", browser_source)
        return None


@asynccontextmanager
async def open_web_fetch_escalation_context(
    *,
    session_id: str,
    browser_source: str | None,
) -> AsyncIterator[None]:
    """Bind L4 providers and browser launch mode for one agent stream run."""
    from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools

    providers = await build_escalation_providers(session_id)
    launch_mode = resolve_browser_launch_mode(browser_source)

    with bind_web_fetch_escalation_context(providers=providers, launch_mode=launch_mode):
        web_fetch_tools.set_escalation_providers(providers)
        web_fetch_tools.set_browser_launch_mode(launch_mode)
        try:
            yield
        finally:
            web_fetch_tools.set_escalation_providers(None)
            web_fetch_tools.set_browser_launch_mode(None)
