"""What a page opens or asks while the Agent works in the user's browser: new tabs and JavaScript dialogs.

[INPUT]
- conftest::stack (POS: the unpacked extension connected to the production bridge, plus a login-gated fixture site)
- tests.support.extension_real_browser::new_agent_page (POS: a context and page the way the Agent's browser pool opens them)

[OUTPUT]
- a click that opens a new tab (a link with target=_blank, window.open) hands the Agent that page, with its opener and
  its load event, also when the Agent's tab is behind the user's; closing it closes the tab in the user's browser; a tab
  the user's own tab opens never becomes the Agent's; a tab such a click opens on a site the user did not authorize
  (directly or through a redirect) is never handed to the Agent, and a page that leaves the authorized sites while the
  Agent's client sets it up is let go without harming the Agent's connection; the Agent's BrowserSession follows such a
  click to the new tab and back; a confirm dialog is answered through the relay

[POS]
The end-to-end proof that the Agent is not left blind after a click. The relay and extension unit tests cannot show it:
only real Chromium opens the tab, names its opener and raises the dialog, and only real Playwright turns those into
the popup event and the dialog event the Agent's tools wait for.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import quote, urlparse

import pytest
from myrm_agent_harness.toolkits.browser.session import BrowserSession
from patchright.async_api import Browser, Dialog, Page
from patchright.async_api import Error as PlaywrightError

from tests.support.extension_real_browser import INTRANET_HOST, OTHER_HOST, RealExtensionStack, new_agent_page, wait_until

pytestmark = pytest.mark.e2e

_LATE_BOUNCE_DELAYS_MS = [10, 15, 20, 25, 30, 35, 40, 50] * 3


async def _popup_after_clicking(page: Page, trigger: str) -> Page:
    async with page.expect_popup() as opened:
        await page.click(trigger)
    popup = await opened.value
    await popup.wait_for_load_state()
    return popup


async def _private_data_of(page: Page) -> str | None:
    """What an Agent that reads every page it is handed, the moment it is handed, gets out of the other site's page."""
    try:
        return await page.inner_text("#data", timeout=3_000)
    except PlaywrightError:
        return None


async def _ref_named(session: BrowserSession, name: str) -> str:
    snapshot = await session.snapshot()
    return next(ref for ref, info in snapshot.refs.items() if info.name == name)


@pytest.mark.parametrize(
    ("trigger", "path", "selector", "text"),
    [
        ("#open-orders", "/orders", "#orders", "Order 1001"),
        ("#open-secret", "/secret", "#data", "private-data-42"),
    ],
    ids=["link-with-target-blank", "window-open"],
)
async def test_a_click_that_opens_a_new_tab_hands_the_agent_that_page(
    stack: RealExtensionStack, trigger: str, path: str, selector: str, text: str
) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/portal"))

        popup = await _popup_after_clicking(page, trigger)

        assert urlparse(popup.url).path == path
        assert await popup.inner_text(selector) == text  # the signed-in page, readable like the one it was opened from
        assert await popup.opener() == page
        assert popup.context == page.context


async def test_every_page_the_agent_opens_by_clicking_in_a_row_reaches_its_load_event(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/portal"))

        for trigger in ("#open-orders", "#open-secret") * 4:
            # The page is often loaded by the time the Agent's browser has it, and its load event must still arrive.
            popup = await _popup_after_clicking(page, trigger)
            await popup.close()


async def test_a_click_in_an_agent_tab_behind_the_users_tab_still_hands_the_agent_its_page(stack: RealExtensionStack) -> None:
    user_tab = await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/portal"))
        await user_tab.bring_to_front()  # the user is back in their own tab; the browser now names it the opener of anything new
        assert (await stack.browser.users_view()).active_url == user_tab.url

        popup = await _popup_after_clicking(page, "#open-orders")

        assert urlparse(popup.url).path == "/orders"
        assert await popup.opener() == page


async def test_closing_the_opened_page_closes_its_tab_in_the_users_browser(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/portal"))
        popup = await _popup_after_clicking(page, "#open-orders")
        opened_url = popup.url
        assert opened_url in stack.browser.user_tab_urls()

        await popup.close()

        async def the_tab_is_gone() -> bool:
            return opened_url not in stack.browser.user_tab_urls()

        await wait_until(the_tab_is_gone, "the opened page's tab to close in the user's browser")
        assert await page.title() == "Portal"  # the page that opened it carries on


async def test_a_tab_the_users_own_tab_opens_never_becomes_the_agents(stack: RealExtensionStack) -> None:
    user_tab = await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    portal, orders = stack.site.url(INTRANET_HOST, "/portal"), stack.site.url(INTRANET_HOST, "/orders")
    await user_tab.goto(portal)

    async with stack.agent_browser() as browser:
        agent_page = await new_agent_page(browser)
        await agent_page.goto(portal)

        await user_tab.click("#open-orders")  # the user's click in the user's tab: nothing says the Agent made it open

        async def the_server_learned_of_the_tab() -> bool:
            return any(tab.url == orders for tab in stack.bridge._tabs)

        await wait_until(the_server_learned_of_the_tab, "the server to learn of the tab the user opened")
        users_new_tab = next(tab for tab in stack.bridge._tabs if tab.url == orders)
        assert users_new_tab.tab_id not in stack.bridge._agent_tabs

        # The Agent's own click still gets its page, so the Agent was listening the whole time.
        popup = await _popup_after_clicking(agent_page, "#open-orders")
        assert popup.url == orders
        agent_urls = [seen.url for context in browser.contexts for seen in context.pages]
        assert agent_urls.count(orders) == 1


async def _outbound_page(stack: RealExtensionStack, browser: Browser) -> Page:
    page = await new_agent_page(browser)
    await page.goto(stack.site.url(INTRANET_HOST, "/outbound"))
    return page


def _watch_pages(page: Page) -> tuple[list[Page], list[asyncio.Task[str | None]]]:
    """Every page the Agent's browser hands over from now on, with a task reading each one's private data on arrival."""
    handed: list[Page] = []
    readers: list[asyncio.Task[str | None]] = []

    def on_page(seen: Page) -> None:
        handed.append(seen)
        readers.append(asyncio.create_task(_private_data_of(seen)))

    page.context.on("page", on_page)
    return handed, readers


async def _click_through_to(stack: RealExtensionStack, page: Page, elsewhere: str, via: list[str]) -> None:
    """Open each address in ``via`` with a click, every one ending on ``elsewhere``, and wait for the user's browser to show it.

    A page is handed over or refused within moments, so many rounds make a race show.
    """
    for visits, address in enumerate(via, start=1):
        await page.evaluate("(href) => { document.querySelector('#leave').href = href; }", address)
        await page.click("#leave")

        async def the_user_landed_on_the_site(visits: int = visits) -> bool:
            return stack.browser.user_tab_urls().count(elsewhere) == visits

        await wait_until(the_user_landed_on_the_site, "the click to open the other site's page in the user's browser")


async def _agent_holds_no_page_of(browser: Browser, host: str) -> None:
    async def holds_none() -> bool:
        return all(urlparse(seen.url).hostname != host for context in browser.contexts for seen in context.pages)

    await wait_until(holds_none, f"the Agent's browser to hold no page of {host}")


@pytest.mark.parametrize("route", ["directly", "through-a-redirect"])
async def test_a_page_a_click_opens_on_an_unauthorized_site_is_never_handed_to_the_agent(
    stack: RealExtensionStack, route: str
) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.log_in(OTHER_HOST)  # signed in there as well: the page has private data to show if the Agent can read it
    await stack.authorize([INTRANET_HOST])
    elsewhere = stack.site.url(OTHER_HOST, "/secret")
    bounce = stack.site.url(INTRANET_HOST, f"/bounce?to={quote(elsewhere, safe='')}")  # an authorized address until it redirects

    async with stack.agent_browser() as browser:
        page = await _outbound_page(stack, browser)
        handed, readers = _watch_pages(page)

        await _click_through_to(stack, page, elsewhere, [elsewhere if route == "directly" else bounce] * 4)
        popup = await _popup_after_clicking(page, "#open-orders")  # the connection survived and still gets its pages

        assert handed == [popup]  # not one page of the other site, not even one that is already gone
        assert [text for text in await asyncio.gather(*readers) if text] == []
        assert stack.browser.user_tab_urls().count(elsewhere) == 4  # the tabs stay open for the user
        if route == "directly":
            assert elsewhere not in await stack.browser.agent_tab_urls()  # and are not the Agent's to close


async def test_a_page_that_leaves_the_authorized_sites_while_the_agent_sets_it_up_is_let_go(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.log_in(OTHER_HOST)
    await stack.authorize([INTRANET_HOST])
    elsewhere = stack.site.url(OTHER_HOST, "/secret")
    # The page is authorized when the Agent is handed it and gone from the authorized sites a moment later, while the
    # Agent's client is still setting it up: the extension refuses the client's commands from then on. How long that
    # moment is depends on the machine's pace, so the delays sweep the stretch the setup takes.
    late_bounces = [
        stack.site.url(INTRANET_HOST, f"/late-bounce?after={delay}&to={quote(elsewhere, safe='')}")
        for delay in _LATE_BOUNCE_DELAYS_MS
    ]

    async with stack.agent_browser() as browser:
        page = await _outbound_page(stack, browser)
        handed, readers = _watch_pages(page)

        await _click_through_to(stack, page, elsewhere, late_bounces)

        await _agent_holds_no_page_of(browser, OTHER_HOST)
        assert await page.title() == "Outbound"  # the connection survived the refusals
        await page.click("#open-orders")

        async def the_orders_page_arrived() -> bool:
            return any(urlparse(seen.url).path == "/orders" and not seen.is_closed() for seen in handed)

        await wait_until(the_orders_page_arrived, "the Agent to be handed the page its next click opened")
        assert [text for text in await asyncio.gather(*readers) if text] == []


async def test_session_follows_a_click_that_opens_a_new_tab_and_returns_when_it_closes(stack: RealExtensionStack) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    orders = stack.site.url(INTRANET_HOST, "/orders")

    async with stack.agent_session() as session:
        await session.navigate(stack.site.url(INTRANET_HOST, "/portal"))
        portal_tab = session.get_active_tab_id()

        await session.interact("click", await _ref_named(session, "Orders"))

        async def the_session_follows_the_new_tab() -> bool:
            return session.get_active_tab_id() != portal_tab

        await wait_until(the_session_follows_the_new_tab, "the session to switch to the tab the click opened")
        await session.get_active_page().wait_for_selector("#orders")
        assert "Order 1001" in (await session.snapshot()).aria_tree

        await session.close_tab(session.get_active_tab_id())

        async def the_tab_is_gone() -> bool:
            return orders not in stack.browser.user_tab_urls()

        await wait_until(the_tab_is_gone, "the new tab to close in the user's browser")
        assert session.get_active_tab_id() == portal_tab


@pytest.mark.parametrize(
    ("answer", "title"),
    [(Dialog.accept, "yes"), (Dialog.dismiss, "no")],
    ids=["accept", "dismiss"],
)
async def test_a_dialog_the_page_raises_is_answered_through_the_relay(
    stack: RealExtensionStack, answer: Callable[[Dialog], Awaitable[None]], title: str
) -> None:
    await stack.log_in(INTRANET_HOST)
    await stack.authorize([INTRANET_HOST])
    # The test's own driver of the user's browser sees every dialog too and would dismiss it first; a user has no such client.
    stack.browser.context.on("dialog", lambda _dialog: None)

    async with stack.agent_browser() as browser:
        page = await new_agent_page(browser)
        await page.goto(stack.site.url(INTRANET_HOST, "/portal"))
        questions: list[str] = []

        async def on_dialog(dialog: Dialog) -> None:
            questions.append(dialog.message)
            await answer(dialog)

        page.on("dialog", on_dialog)

        await page.click("#ask")

        await page.wait_for_function(f"document.title === '{title}'")
        assert questions == ["sure?"]
