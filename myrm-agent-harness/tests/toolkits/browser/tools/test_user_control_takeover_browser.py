"""A person moves a real page while the model holds refs for it: nothing the model planned may act on the new page."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator

import pytest
from langchain_core.tools import BaseTool
from patchright.async_api import Route

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.tools import create_browser_tools
from myrm_agent_harness.toolkits.browser.tools.user_control_gate import REOBSERVE_NOTICE
from myrm_agent_harness.utils.runtime.user_control import UserControl

pytestmark = pytest.mark.integration

_SHOP = {
    "http://shop.test/cart": "<title>cart</title><button onclick=\"document.title='cart-clicked'\">Confirm</button>",
    "http://shop.test/pay": "<title>pay</title><h1>Payment</h1><button onclick=\"document.title='PAID'\">Confirm</button>",
}
_TWO_STEP_FORM = "<title>step</title><button onclick=\"document.title+='.'\">Next</button>"
# The click keeps the page busy long enough for a person to take over while the script is still on its first step.
_SLOW_STEP_FORM = "<title>step</title><button onclick=\"var t=Date.now();while(Date.now()-t<1500){};document.title+='.'\">Next</button>"
_MOVED_ON = "<title>moved</title><button onclick=\"document.title+='!'\">Next</button>"
_TWO_CLICKS = "await session.interact('click', '{ref}')\nawait session.interact('click', '{ref}')"


@pytest.fixture
async def session() -> AsyncIterator[BrowserSession]:
    pool = GlobalBrowserPool(max_browsers=1)
    await pool.warmup(browsers=1, pages_per_context=1)
    browser_session = BrowserSession(pool, ContextType.AGENT)
    browser_session.user_control = UserControl()
    browser_session.observed_generation = browser_session.user_control.generation
    await browser_session.new_tab("about:blank")
    yield browser_session
    await browser_session.close()
    await pool.shutdown()


@pytest.fixture
def tools(session: BrowserSession) -> dict[str, BaseTool]:
    return {t.name: t for t in create_browser_tools(session)}


async def _serve_shop(session: BrowserSession) -> None:
    async def respond(route: Route) -> None:
        await route.fulfill(status=200, content_type="text/html", body=_SHOP[route.request.url])

    await session.get_active_page().route("http://shop.test/**", respond)


async def _look(tools: dict[str, BaseTool], label: str) -> str:
    """Take a snapshot as the model does and return the ref of the control named `label`."""
    snapshot = str(await tools["browser_snapshot_tool"].ainvoke({"diff": False, "scope": "interactive"}))
    found = re.search(rf"{label}[^\n]*?\[ref=(e\d+)\]", snapshot) or re.search(
        rf"\[ref=(e\d+)\][^\n]*{label}", snapshot
    )
    assert found, snapshot[:400]
    return found.group(1)


async def _title(session: BrowserSession) -> str:
    return await session.get_active_page().title()


class TestRefsHeldAcrossAHandOver:
    @pytest.mark.asyncio
    async def test_reading_the_page_does_not_make_an_old_ref_safe_to_click(
        self, session: BrowserSession, tools: dict[str, BaseTool]
    ) -> None:
        await _serve_shop(session)
        await session.get_active_page().goto("http://shop.test/cart")
        confirm_on_cart = await _look(tools, "Confirm")
        session.user_control.acquire()
        await session.get_active_page().goto("http://shop.test/pay")
        session.user_control.release()

        await tools["browser_extract_tool"].ainvoke({"mode": "text"})
        refused = await tools["browser_interact_tool"].ainvoke({"action": "click", "ref": confirm_on_cart})

        assert refused == REOBSERVE_NOTICE
        assert await _title(session) == "pay", "the old ref must not reach the payment page"

    @pytest.mark.asyncio
    async def test_a_fresh_snapshot_lets_the_model_act_on_the_page_it_now_sees(
        self, session: BrowserSession, tools: dict[str, BaseTool]
    ) -> None:
        await _serve_shop(session)
        await session.get_active_page().goto("http://shop.test/cart")
        await _look(tools, "Confirm")
        session.user_control.acquire()
        await session.get_active_page().goto("http://shop.test/pay")
        session.user_control.release()

        confirm_on_pay = await _look(tools, "Confirm")
        await tools["browser_interact_tool"].ainvoke({"action": "click", "ref": confirm_on_pay})

        assert await _title(session) == "PAID"


class TestScriptsAcrossAHandOver:
    @pytest.mark.asyncio
    async def test_a_script_runs_every_step_when_nobody_takes_over(
        self, session: BrowserSession, tools: dict[str, BaseTool]
    ) -> None:
        await session.get_active_page().set_content(_TWO_STEP_FORM)
        next_ref = await _look(tools, "Next")

        await tools["browser_execute_script_tool"].ainvoke({"script": _TWO_CLICKS.format(ref=next_ref)})

        assert await _title(session) == "step.."

    @pytest.mark.asyncio
    async def test_a_script_stops_before_a_step_the_person_moved_the_page_under(
        self, session: BrowserSession, tools: dict[str, BaseTool]
    ) -> None:
        page = session.get_active_page()
        await page.set_content(_SLOW_STEP_FORM)
        next_ref = await _look(tools, "Next")
        script = asyncio.create_task(
            tools["browser_execute_script_tool"].ainvoke({"script": _TWO_CLICKS.format(ref=next_ref)})
        )

        await asyncio.sleep(0.5)  # the first step is still clicking
        session.user_control.acquire()
        await page.set_content(_MOVED_ON)
        session.user_control.release()
        result = str(await asyncio.wait_for(script, timeout=30.0))

        assert await _title(session) == "moved", "the second step must not click on the page the person moved to"
        assert "a person used the browser while it was running" in result

    @pytest.mark.asyncio
    async def test_a_script_started_after_the_model_looked_again_runs_every_step(
        self, session: BrowserSession, tools: dict[str, BaseTool]
    ) -> None:
        await session.get_active_page().set_content(_TWO_STEP_FORM)
        session.user_control.acquire()
        session.user_control.release()
        next_ref = await _look(tools, "Next")

        await tools["browser_execute_script_tool"].ainvoke({"script": _TWO_CLICKS.format(ref=next_ref)})

        assert await _title(session) == "step.."
