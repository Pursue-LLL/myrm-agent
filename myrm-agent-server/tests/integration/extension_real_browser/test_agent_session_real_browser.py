"""The Agent's browser session in a real Chromium: Playwright over the production bridge and its CDP relay.

[INPUT]
- conftest::stack (POS: the unpacked extension connected to the production bridge, plus a login-gated fixture site)
- tests.support.extension_real_browser::new_agent_page (POS: a context and page the way the Agent's browser pool opens them)

[OUTPUT]
- what an Agent session does with the user's signed-in browser: read a logged-in page, click, take a screenshot; where
  it is stopped (a domain the user did not authorize, a page that is not a web page); how its tabs are marked, kept
  apart from the user's list and closed; and that the user's own tabs are never closed on its behalf

[POS]
The end-to-end proof of the extension's one job. The relay and extension unit tests mock the other side, so only these
tests notice when real Playwright, the relay and the extension stop agreeing on target ids, contexts or tab ownership.
"""

from __future__ import annotations

import asyncio

import pytest
from patchright.async_api import Error as PlaywrightError

from tests.support.extension_real_browser import (
    INTRANET_HOST,
    OTHER_HOST,
    RealExtensionStack,
    find_page,
    new_agent_page,
    wait_until,
)

pytestmark = pytest.mark.e2e

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
AGENT_GROUP_TITLE = "Myrm Agent"

_GROUPS_SCRIPT = """async () => {
  const groups = await chrome.tabGroups.query({});
  return Promise.all(groups.map(async (group) => ({
    title: group.title,
    urls: (await chrome.tabs.query({ groupId: group.id })).map((tab) => tab.url),
  })));
}"""


async def _tab_groups(stack: RealExtensionStack) -> list[dict[str, str | list[str]]]:
    groups = await stack.browser.evaluate(_GROUPS_SCRIPT)
    assert isinstance(groups, list)
    return groups


async def test_agent_reads_a_signed_in_page_and_acts_on_it(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/secret"))

        assert await page.title() == "Secret"  # the user's session cookie reached the page
        assert await page.inner_text("#data") == "private-data-42"

        await page.click("#orders-link")
        await page.wait_for_selector("#orders")
        await page.click("#confirm")
        assert await page.title() == "confirmed"
        assert (await page.screenshot()).startswith(PNG_SIGNATURE)


async def test_agent_page_cannot_leave_the_authorized_domains(stack: RealExtensionStack) -> None:
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)

        with pytest.raises(PlaywrightError, match="not authorized"):
            await page.goto(stack.site.url(OTHER_HOST, "/secret"))

        assert page.url == "about:blank"


async def test_agent_can_take_its_own_page_back_to_blank_but_never_a_users(stack: RealExtensionStack) -> None:
    user_tab = await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/secret"))

        await page.goto("about:blank")  # the browser pool resets a reused page this way
        await page.goto(stack.site.url(INTRANET_HOST, "/secret"))
        assert await page.inner_text("#data") == "private-data-42"

        borrowed = find_page(browser, "/login")
        with pytest.raises(PlaywrightError, match="not authorized"):
            await borrowed.goto("about:blank")

    assert "/login" in user_tab.url


async def test_agent_cannot_open_a_tab_on_an_unauthorized_or_non_web_page(stack: RealExtensionStack) -> None:
    await stack.authorize([INTRANET_HOST])
    tabs_before = stack.browser.user_tab_urls()

    async with stack.agent_browser() as browser:
        session = await browser.new_browser_cdp_session()
        for url in (stack.site.url(OTHER_HOST, "/secret"), "data:text/html,<p>unreviewed</p>", "javascript:alert(1)"):
            with pytest.raises(PlaywrightError, match="not authorized"):
                await session.send("Target.createTarget", {"url": url})

    assert stack.browser.user_tab_urls() == tabs_before


async def test_closing_a_page_closes_the_agents_tab_but_only_lets_go_of_a_users(stack: RealExtensionStack) -> None:
    user_tab = await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/secret"))
        tabs_open = len(stack.browser.user_tab_urls())

        await page.close()

        async def agent_tab_closed() -> bool:
            return len(stack.browser.user_tab_urls()) == tabs_open - 1

        await wait_until(agent_tab_closed, "the Agent's tab to close with its page")

        borrowed = find_page(browser, "/login")
        await asyncio.wait_for(borrowed.close(), timeout=20)  # Playwright waits for the target to go away
        assert borrowed.is_closed()

    assert not user_tab.is_closed()
    assert any("/login" in url for url in stack.browser.user_tab_urls())


async def test_agent_tabs_wear_one_group_the_user_can_recognise(stack: RealExtensionStack) -> None:
    user_tab = await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        context = await browser.new_context()
        pages = await asyncio.gather(*(context.new_page() for _ in range(3)))
        for page in pages:
            await page.goto(stack.site.url(INTRANET_HOST, "/orders"))

        async def one_group_holds_the_agent_tabs() -> bool:
            groups = await _tab_groups(stack)
            return len(groups) == 1 and len(groups[0]["urls"]) == len(pages)

        await wait_until(one_group_holds_the_agent_tabs, "the three Agent tabs to share one tab group")

        (group,) = await _tab_groups(stack)
        assert group["title"] == AGENT_GROUP_TITLE
        assert user_tab.url not in group["urls"]


async def test_a_blank_agent_tab_is_not_listed_as_one_of_the_users(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        await new_agent_page(browser)

        listed = await stack.bridge.list_tabs()

        assert [tab.domain for tab in listed] == [INTRANET_HOST]
