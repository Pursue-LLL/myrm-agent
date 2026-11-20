"""Real-Chromium proof that a same-origin popup obeys the allowlist on the channels no request filter sees.

``window.open(url)`` to the opener's own origin reuses the popup's initial ``about:blank`` window: the init scripts
ran there once and what they set on the window stays, but the document is new and normally carries no CSP
``<meta>``. WebSocket and the Workers that run script from a blob or data URL are the channels Layer 1 never sees, so
without the policy they could reach any host from that document. A second loopback server stands for such a host and
records every request it receives, so a route that connects shows up there. Each route runs alone, as the first
channel a fresh document opens, once in a navigated tab (a document that carries the policy from its first byte) and
once in a popup; the popup must answer it as the tab does. Run with:
`pytest -m integration tests/toolkits/browser/test_popup_channel_policy_integration.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist
from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.utils.private_origins import private_origin_grants
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._redirect_servers import Site, page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_MAIN_WORLD = {"isolated_context": False}
_TIMEOUT_MS = 15_000
# Popups the policy-once test opens at most while it looks for one that starts without a policy; a heavily loaded
# machine needs many tries because the init script then often reaches a popup's document after its page's first script.
_POPUP_ATTEMPTS = 20

# The ways a page can open a WebSocket or a Worker. ``allowed`` goes to the allowlisted site; every other route goes to
# the outside server: the constructor itself, the routes that reach the native constructor around a wrapper
# (``prototype.constructor``, an instance's ``constructor``, a subclass, ``Reflect.construct``, another realm) and the
# Workers whose script comes from a blob or data URL and opens the socket itself. A refusal arrives as a policy
# violation, not as an exception, so the verdict keeps both.
_ROUTES = (
    "allowed",
    "direct",
    "prototype_constructor",
    "instance_constructor",
    "subclass",
    "reflect",
    "frame_realm",
    "blob_worker",
    "data_worker",
    "blob_shared_worker",
)
_PROBE = r"""
async ([route, outsideBase, insideBase]) => {
  const outside = (path) => `${outsideBase.replace('http', 'ws')}/${path}`;
  const inside = (path) => `${insideBase.replace('http', 'ws')}/${path}`;
  const script = `new WebSocket('${outside('worker')}')`;
  const blob = () => URL.createObjectURL(new Blob([script], {type: 'text/javascript'}));
  const routes = {
    allowed: () => new WebSocket(inside('allowed')),
    direct: () => new WebSocket(outside(route)),
    prototype_constructor: () => new WebSocket.prototype.constructor(outside(route)),
    instance_constructor: () => new (new WebSocket.prototype.constructor(inside('seed'))).constructor(outside(route)),
    subclass: () => { class Tap extends WebSocket {} return new Tap(outside(route)); },
    reflect: () => Reflect.construct(WebSocket, [outside(route)]),
    frame_realm: () => {
      const frame = document.body.appendChild(document.createElement('iframe'));
      return new frame.contentWindow.WebSocket(outside(route));
    },
    blob_worker: () => new Worker(blob()),
    data_worker: () => new Worker(`data:text/javascript,${encodeURIComponent(script)}`),
    blob_shared_worker: () => new SharedWorker(blob()),
  };
  const violations = [];
  document.addEventListener('securitypolicyviolation', (e) => violations.push(e.violatedDirective));
  let outcome;
  try { routes[route](); outcome = 'opened'; } catch (e) { outcome = e.name; }
  await new Promise((resolve) => setTimeout(resolve, 400));
  return {outcome, violations};
}
"""
_POLICY_COUNT = "document.head.querySelectorAll('meta[http-equiv]').length"
_OPEN_CHANNELS_TWICE = f"""() => {{
  new WebSocket(location.origin.replace('http', 'ws') + '/a');
  new Worker('data:,');
  return {_POLICY_COUNT};
}}"""


@pytest.fixture
def sites() -> Iterator[tuple[Site, Site]]:
    """The allowlisted site and a second server for the allowlist to keep out."""
    with serve({"/": page("home")}) as inside, serve({"/": page("outside")}) as outside:
        yield inside, outside


@asynccontextmanager
async def _tab(site: Site) -> AsyncIterator[Page]:
    """A tab in a context of the pool, as production builds it: a domain allowlist holding only ``site``'s host."""
    pool = GlobalBrowserPool(max_browsers=1, config=BrowserPoolConfig.minimal())
    allowlist = DomainAllowlist.from_strings(("127.0.0.1",))
    tab, context_key = await pool.acquire_page(
        ContextType.AGENT, context_kwargs={"domain_allowlist": allowlist, "allow_private_networks": True}
    )
    private_origin_grants(tab.context).grant(site.base_url)
    # Chromium's Local Network Access would stop one loopback server from reaching another whatever the allowlist
    # says, which would hide a connection the policy failed to refuse.
    await tab.context.grant_permissions(["local-network-access"])
    try:
        yield tab
    finally:
        await pool.release_page(tab, context_key)
        await pool.shutdown()


async def _open_popup(tab: Page, site: Site) -> Page:
    """``window.open`` to the tab's own origin, returned once the popup shows that site's document."""
    async with tab.context.expect_page(timeout=_TIMEOUT_MS) as popup_info:
        await tab.evaluate("window.open('/')", **_MAIN_WORLD)
    popup = await popup_info.value
    # The popup starts as ``about:blank``, which counts as loaded: wait for the document under test.
    await popup.wait_for_url(site.url("/"), timeout=_TIMEOUT_MS)
    return popup


async def _open_popup_without_policy(tab: Page, site: Site) -> Page | None:
    """A popup whose document has no policy yet, so the test can watch it get one; ``None`` if none does.

    The init script usually runs on a same-origin popup's initial window before its document arrives, which leaves the
    document without a policy until a wrapped constructor adds one. The driver lets a popup start before it has
    registered the init scripts, so now and then the script reaches the document after the page's first script and the
    policy is already there: that document cannot show how the policy gets added, so it is closed and another opened.
    """
    for _ in range(_POPUP_ATTEMPTS):
        popup = await _open_popup(tab, site)
        if await popup.evaluate(_POLICY_COUNT, **_MAIN_WORLD) == 0:
            return popup
        await popup.close()
    return None


async def test_each_route_in_a_same_origin_popup_ends_as_it_does_in_a_navigated_tab(sites: tuple[Site, Site]) -> None:
    inside, outside = sites
    # ``localhost`` is not on the allowlist, which holds ``127.0.0.1``: the outside server is a different host.
    targets = [outside.base_url.replace("127.0.0.1", "localhost"), inside.base_url]
    tab_verdicts: dict[str, object] = {}
    popup_verdicts: dict[str, object] = {}
    async with _tab(inside) as tab:
        for route in _ROUTES:
            await tab.goto(inside.url("/"), timeout=_TIMEOUT_MS)
            tab_verdicts[route] = await tab.evaluate(_PROBE, [route, *targets], **_MAIN_WORLD)
            popup = await _open_popup(tab, inside)
            popup_verdicts[route] = await popup.evaluate(_PROBE, [route, *targets], **_MAIN_WORLD)
            await popup.close()

    assert outside.hits == []
    assert popup_verdicts == tab_verdicts
    assert inside.paths("GET").count("/allowed") == 2


async def test_a_document_gets_its_policy_once(sites: tuple[Site, Site]) -> None:
    inside, _ = sites
    async with _tab(inside) as tab:
        await tab.goto(inside.url("/"), timeout=_TIMEOUT_MS)
        assert await tab.evaluate(_OPEN_CHANNELS_TWICE, **_MAIN_WORLD) == 1
        popup = await _open_popup_without_policy(tab, inside)
        if popup is None:
            # A skip shows in CI only as "skipped", so the half of the check that never ran would go unnoticed.
            pytest.fail(
                f"all {_POPUP_ATTEMPTS} popups already had a policy when the test first looked: either a popup "
                "document now gets its policy before its page opens a channel, so the half of the check that needs one "
                "without it no longer applies, or the machine is so loaded that the init script keeps arriving late "
                "(run it again on a quieter one)"
            )
        assert await popup.evaluate(_OPEN_CHANNELS_TWICE, **_MAIN_WORLD) == 1
