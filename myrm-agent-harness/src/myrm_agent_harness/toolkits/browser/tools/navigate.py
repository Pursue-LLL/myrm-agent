"""browser_navigate tool for URL navigation.

[INPUT]
- common::mark_untrusted (POS: unified browser output security boundary; credential redaction + untrusted-content wrapping)
- tools.download_actions::describe_downloads_since (POS: agent-facing text of the download actions)
- utils.errors::ToolError (POS: Storage quota related errors.)

[OUTPUT]
- create_navigate_tool: Create browser_navigate tool bound to session; successful navigate returns `{content, metadata:{sources:[{url,title,source_key}]}}` for SourceTracker.

[POS]
browser_navigate tool for URL navigation. An address that answers with a file makes the browser start a download
instead of opening a page, which fails the navigation; the answer then says what the download came to, so the agent
does not read a saved file as a failure and retry (a retry saves the file a second time).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.tools import tool
from pydantic import BaseModel, Field

from ..exceptions import BrowserNavigationError
from .common import mark_untrusted
from .download_actions import describe_downloads_since

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool

    from ..session import BrowserSession

_STARTED_A_DOWNLOAD = "The address started a file download instead of opening a page."


def create_navigate_tool(session: BrowserSession) -> BaseTool:
    """Create browser_navigate tool bound to session."""

    class NavigateInput(BaseModel):
        url: str = Field(description="Target URL to navigate to (e.g. 'https://example.com')")
        verify_goal: str | None = Field(
            default=None,
            description="Optional natural language description of expected visual state after navigation (e.g. 'Login form is visible', 'Search results loaded'). Automatically verifies visual outcome and returns feedback.",
        )

    from myrm_agent_harness.utils.tool_dynamic_hints import with_dynamic_hints

    @tool("browser_navigate_tool", args_schema=NavigateInput)
    async def browser_navigate(url: str, verify_goal: str | None = None) -> str | dict[str, object]:
        """Open a URL in the browser. Returns page title, final URL, and status code.

        After navigation, call browser_snapshot_tool to inspect the page structure and get element refs before interacting.
        """
        # URL data exfiltration detection (P0 Critical Security)
        import logging

        from myrm_agent_harness.utils.errors import ToolError
        from myrm_agent_harness.utils.url_utils import check_url_exfiltration, sanitize_url_for_error

        warnings = check_url_exfiltration(url, allow_private_networks=True)
        if warnings:
            logger = logging.getLogger(__name__)
            safe_url = sanitize_url_for_error(url)
            logger.warning(f" Data exfiltration detected in browser_navigate: {safe_url}")
            for warning in warnings:
                logger.warning(f"  - {warning}")
            raise ToolError(
                f"Navigation blocked (data exfiltration): {'; '.join(warnings)} — URL: {safe_url}",
                user_hint="The URL contains sensitive data (API keys, file paths, or credentials). Remove sensitive data from the URL.",
            )

        mark = session.download_mark()
        try:
            raw_result = await session.navigate(url, verify_goal=verify_goal)
        except BrowserNavigationError:
            if notes := await describe_downloads_since(session, mark):
                return mark_untrusted(f"{_STARTED_A_DOWNLOAD}\n{notes}")
            raise
        content = mark_untrusted(raw_result)
        page = session.get_active_page()
        page_url = page.url
        page_title = await page.title()
        sources: list[dict[str, object]] = [
            {
                "type": "web_fetch",
                "url": page_url,
                "title": page_title or page_url,
                "source_key": f"browser:{page_url}",
            }
        ]
        return {"content": content, "metadata": {"sources": sources}}

    return with_dynamic_hints(
        browser_navigate,
        {
            "web_search_tool": "For simple information retrieval, prefer web_search_tool (faster, cheaper).",
            "web_fetch_tool": "For read-only content retrieval (no interaction needed), prefer web_fetch_tool (faster, cheaper, handles JS internally).",
        },
    )
