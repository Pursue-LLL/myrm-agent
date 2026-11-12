"""The Agent's BrowserSession on the user's own browser, through the production pool, bridge, relay and extension.

[INPUT]
- conftest::stack (POS: the unpacked extension connected to the production bridge, plus a login-gated fixture site)
- tests.support.extension_real_browser::RealExtensionStack.agent_session (POS: BrowserSession on the production browser pool)

[OUTPUT]
- what the Agent's browsing tools do in the user's signed-in browser: navigate, read, click, take a screenshot; where
  they are stopped; which tabs they leave behind (none, once the session ends)

[POS]
The top of the end-to-end proof: the harness's own context options, page pool and session logic run against the real
extension, so a harness option the extension cannot honour fails here instead of in the user's browser.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.browser.exceptions import BrowserNavigationError
from myrm_agent_harness.toolkits.browser.session import BrowserSession

from tests.support.extension_real_browser import INTRANET_HOST, OTHER_HOST, RealExtensionStack, wait_until

pytestmark = pytest.mark.e2e

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


async def _ref_named(session: BrowserSession, name: str) -> str:
    snapshot = await session.snapshot()
    return next(ref for ref, info in snapshot.refs.items() if info.name == name)


async def test_session_navigates_to_a_signed_in_page_and_reads_it(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_session() as session:
        result = await session.navigate(stack.site.url(INTRANET_HOST, "/secret"))

        assert "Secret" in result
        assert "private-data-42" in (await session.snapshot()).aria_tree
        assert (await session.get_final_screenshot()).startswith(PNG_SIGNATURE)


async def test_session_clicks_through_the_signed_in_site(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_session() as session:
        await session.navigate(stack.site.url(INTRANET_HOST, "/secret"))
        await session.interact("click", await _ref_named(session, "Orders"))
        await session.get_active_page().wait_for_selector("#orders")
        await session.interact("click", await _ref_named(session, "Confirm"))

        assert await session.get_active_page().title() == "confirmed"


async def test_session_is_stopped_at_a_domain_the_user_did_not_authorize(stack: RealExtensionStack) -> None:
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_session() as session:
        with pytest.raises(BrowserNavigationError, match="not authorized"):
            await session.navigate(stack.site.url(OTHER_HOST, "/secret"))


async def test_session_leaves_no_tab_of_its_own_behind_and_keeps_the_users(stack: RealExtensionStack) -> None:
    user_tab = await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    tabs_before = sorted(stack.browser.user_tab_urls())

    async with stack.agent_session() as session:
        await session.navigate(stack.site.url(INTRANET_HOST, "/secret"))
        await session.new_tab()
        await session.navigate(stack.site.url(INTRANET_HOST, "/orders"))
        assert len(stack.browser.user_tab_urls()) == len(tabs_before) + 2

    async def only_the_users_tabs_remain() -> bool:
        return sorted(stack.browser.user_tab_urls()) == tabs_before

    await wait_until(only_the_users_tabs_remain, "the Agent's tabs to close with its session")
    assert not user_tab.is_closed()
