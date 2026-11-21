"""Real-Chromium proof that the agent's own JavaScript runs under the allowlist the page's scripts run under.

``BrowserSession.evaluate`` hands the expression to ``page.evaluate``, which runs it in the driver's isolated world:
constructors and a window of its own over the page's DOM. The init scripts of Layers 0 and 2 run in the page's main
world, so their wrappers and hardening are not there, and a document with no policy ``<meta>`` (a same-origin popup's
reused window) would let the expression open a WebSocket or a Worker to any host. ``domain_filter.agent_world`` arms the
window before the expression runs. Every test calls ``BrowserSession.evaluate`` as the agent does, on a context built
the way production builds it. A second loopback server records every request it receives and a UDP socket every
datagram, so a channel that reaches outside shows up there. Run with:
`pytest -m integration tests/toolkits/browser/test_agent_world_policy_integration.py`.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterator

import pytest
from patchright.async_api import Error as BrowserError
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.domain_filter.agent_world import agent_world_expression
from tests.toolkits.browser._allowlisted_session import allowlisted_session
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._channel_probe import CHANNEL_ROUTES, probe_expression
from tests.toolkits.browser._redirect_servers import Reply, Site, page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_TIMEOUT_MS = 15_000
_MAIN_WORLD = {"isolated_context": False}
_POLICY_COUNT = "document.head.querySelectorAll('meta[http-equiv]').length"
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _html(text: str, *headers: tuple[str, str]) -> Reply:
    return Reply(
        body=f"<!DOCTYPE html><html><head><title>{text}</title></head><body>{text}</body></html>".encode(),
        headers=headers,
    )


# Documents the agent may find itself in. A text, JSON or image document is built as HTML around its content; an XML or
# SVG document has no head until the policy script gives it one.
_DOCUMENTS = {
    "/": page("home"),
    "/plain": Reply(body=b"plain text", content_type="text/plain; charset=utf-8"),
    "/json": Reply(body=b'{"a": 1}', content_type="application/json"),
    "/fragment": Reply(body=b"<p>fragment, no html, head or body tags</p>"),
    "/xhtml": Reply(
        body=b'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title></head><body>x</body></html>',
        content_type="application/xhtml+xml",
    ),
    "/png": Reply(body=_PNG, content_type="image/png"),
    "/strict": _html("strict", ("Content-Security-Policy", "script-src 'self'")),
    "/trusted": _html("trusted", ("Content-Security-Policy", "require-trusted-types-for 'script'")),
    "/xml": Reply(body=b'<?xml version="1.0"?><root><item>x</item></root>', content_type="application/xml"),
    "/svg": Reply(
        body=b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>',
        content_type="image/svg+xml",
    ),
}


@pytest.fixture
def sites() -> Iterator[tuple[Site, Site]]:
    """The allowlisted site and a second server for the allowlist to keep out."""
    routes = {**_DOCUMENTS, "/sw.js": Reply(body=b"self.onfetch = () => {};", content_type="text/javascript")}
    with serve(routes) as inside, serve({"/": page("outside")}) as outside:
        yield inside, outside


async def _open_popup(session: BrowserSession, site: Site) -> Page:
    """``window.open`` from the active tab to its own origin; the popup, once it is the session's active tab."""
    opener = session.get_active_page()
    async with opener.context.expect_page(timeout=_TIMEOUT_MS) as popup_info:
        await session.evaluate("(() => { window.open('/'); return 'opened'; })()")
    popup = await popup_info.value
    await popup.wait_for_url(site.url("/"), timeout=_TIMEOUT_MS)
    for _ in range(100):  # the tab controller adopts the popup from the opener's popup event
        if session.get_active_page() is popup:
            return popup
        await asyncio.sleep(0.05)
    raise AssertionError("the session never made the popup its active tab")


# ---------------------------------------------------------------------------------------------------------------------
# WebSocket and Worker: the browser's policy, put on the document before the agent's script runs
# ---------------------------------------------------------------------------------------------------------------------


async def test_each_route_in_a_same_origin_popup_ends_as_it_does_in_a_navigated_tab(sites: tuple[Site, Site]) -> None:
    """The tab's document carries the policy from its first byte; the popup's reused window does not."""
    inside, outside = sites
    # ``localhost`` is not on the allowlist, which holds ``127.0.0.1``: the outside server is a different host.
    targets = (outside.base_url.replace("127.0.0.1", "localhost"), inside.base_url)
    tab_verdicts: dict[str, str] = {}
    popup_verdicts: dict[str, str] = {}
    async with allowlisted_session(inside) as session:
        tab = session.get_active_page()
        for route in CHANNEL_ROUTES:
            await session.navigate(inside.url("/"))
            tab_verdicts[route] = await session.evaluate(probe_expression(route, *targets))
            popup = await _open_popup(session, inside)
            popup_verdicts[route] = await session.evaluate(probe_expression(route, *targets))
            await popup.close()
            assert session.get_active_page() is tab

    assert outside.hits == []
    assert popup_verdicts == tab_verdicts
    assert inside.paths("GET").count("/allowed") == 2


# ---------------------------------------------------------------------------------------------------------------------
# RTCPeerConnection, WebTransport and Service Worker registration: the hardening, in the agent's own window
# ---------------------------------------------------------------------------------------------------------------------

_RTC = """(async () => {
  try {
    const pc = new RTCPeerConnection({iceServers: [{urls: 'stun:127.0.0.1:__PORT__'}]});
    pc.createDataChannel('probe');
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((resolve) => setTimeout(resolve, 1500));
    return 'constructed';
  } catch (e) { return e.name; }
})()"""
_WEB_TRANSPORT = (
    "(() => { try { new WebTransport('https://127.0.0.1:9'); return 'constructed'; } catch (e) { return e.name; } })()"
)
_SERVICE_WORKER = """(async () => {
  try { await navigator.serviceWorker.register('/sw.js'); return 'registered'; } catch (e) { return e.name; }
})()"""


class _Datagrams(asyncio.DatagramProtocol):
    """A UDP socket on loopback that counts what reaches it: the STUN requests an unrefused RTCPeerConnection sends."""

    def __init__(self) -> None:
        self.count = 0

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.count += 1


async def test_the_channels_the_policy_hardens_stay_closed_in_a_tab_and_in_a_popup(sites: tuple[Site, Site]) -> None:
    inside, _ = sites
    datagrams = _Datagrams()
    transport, _protocol = await asyncio.get_running_loop().create_datagram_endpoint(
        lambda: datagrams, local_addr=("127.0.0.1", 0)
    )
    try:
        rtc = _RTC.replace("__PORT__", str(transport.get_extra_info("sockname")[1]))
        verdicts: dict[str, list[str]] = {}
        async with allowlisted_session(inside) as session:
            await session.navigate(inside.url("/"))
            for where in ("tab", "popup"):
                if where == "popup":
                    await _open_popup(session, inside)
                verdicts[where] = [await session.evaluate(probe) for probe in (rtc, _WEB_TRANSPORT, _SERVICE_WORKER)]
    finally:
        transport.close()

    assert verdicts == {"tab": ["SecurityError"] * 3, "popup": ["SecurityError"] * 3}
    assert datagrams.count == 0


# ---------------------------------------------------------------------------------------------------------------------
# One policy per document, whichever world put it there
# ---------------------------------------------------------------------------------------------------------------------


async def test_the_arm_adds_no_second_policy_to_a_document_that_has_one(sites: tuple[Site, Site]) -> None:
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        await session.navigate(inside.url("/"))
        assert await session.evaluate(_POLICY_COUNT) == "1"  # the page's world put it there; the arm only checks
        assert await session.evaluate(_POLICY_COUNT) == "1"  # a window armed once is not armed again

        popup = await _open_popup(session, inside)
        assert await session.evaluate(_POLICY_COUNT) == "1"
        # The page's own wrappers add the policy when they find it missing: they must find the agent world's.
        opened = (
            "() => { new WebSocket(location.origin.replace('http', 'ws') + '/a'); new Worker('data:,'); return 1; }"
        )
        await popup.evaluate(opened, **_MAIN_WORLD)
        assert await session.evaluate(_POLICY_COUNT) == "1"


async def test_the_agent_cannot_take_the_arm_down_for_the_calls_that_follow(sites: tuple[Site, Site]) -> None:
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        await session.navigate(inside.url("/"))
        assert await session.evaluate("delete globalThis.__myrmDomainPolicy") == "False"
        overwrite = "(() => { const arm = globalThis.__myrmDomainPolicy; globalThis.__myrmDomainPolicy = () => true; return arm === globalThis.__myrmDomainPolicy; })()"
        assert await session.evaluate(overwrite) == "True"
        assert await session.evaluate(_WEB_TRANSPORT) == "SecurityError"


async def test_the_first_call_succeeds_in_a_window_the_init_scripts_already_hardened(sites: tuple[Site, Site]) -> None:
    """An engine whose ``evaluate`` runs in the page's own world has the hardening in place when the arm first runs."""
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        tab = session.get_active_page()
        await session.navigate(inside.url("/"))
        armed = agent_world_expression(tab.context, _WEB_TRANSPORT)
        assert [await tab.evaluate(armed, **_MAIN_WORLD) for _ in range(2)] == ["SecurityError"] * 2


# ---------------------------------------------------------------------------------------------------------------------
# What kind of document the script may run in
# ---------------------------------------------------------------------------------------------------------------------


async def test_the_script_runs_in_every_kind_of_document(sites: tuple[Site, Site]) -> None:
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        for path in _DOCUMENTS:
            await session.navigate(inside.url(path))
            assert await session.evaluate("1 + 1") == "2", path


async def test_a_document_with_no_root_element_refuses_the_script(sites: tuple[Site, Site]) -> None:
    """With no root element there is nowhere to put the policy: the script is refused rather than run with none on it."""
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        tab = session.get_active_page()
        await session.navigate(inside.url("/"))
        await tab.evaluate("document.documentElement.remove()")
        with pytest.raises(BrowserError, match="JS evaluation refused"):
            await session.evaluate("1 + 1")


async def test_a_parsed_document_with_no_head_is_given_one_and_not_left_watched(sites: tuple[Site, Site]) -> None:
    """The script waits for a head only while the parser may still create one; a parsed document gets its head at once."""
    inside, _ = sites
    spy = """() => {
        const observe = MutationObserver.prototype.observe;
        globalThis.__observed = 0;
        MutationObserver.prototype.observe = function (...args) {
            globalThis.__observed += 1;
            return observe.apply(this, args);
        };
    }"""
    async with allowlisted_session(inside) as session:
        tab = session.get_active_page()
        await session.navigate(inside.url("/svg"))
        await tab.evaluate(spy)  # in the isolated world the agent's script runs in, before the arm is there
        assert await session.evaluate("1 + 1") == "2"
        assert await tab.evaluate("globalThis.__observed") == 0


async def test_a_document_with_no_head_gets_one_head_and_one_policy_however_often_the_script_runs(
    sites: tuple[Site, Site],
) -> None:
    inside, _ = sites
    counts = (
        "[document.documentElement.getElementsByTagNameNS('http://www.w3.org/1999/xhtml', 'head').length,"
        " document.querySelectorAll('meta[http-equiv]').length].join()"
    )
    async with allowlisted_session(inside) as session:
        for path in ("/xml", "/svg"):
            await session.navigate(inside.url(path))
            for _ in range(3):
                assert await session.evaluate("1 + 1") == "2", path
            assert await session.evaluate(counts) == "1,1", path


# ---------------------------------------------------------------------------------------------------------------------
# The script itself: the same answer as without the arm
# ---------------------------------------------------------------------------------------------------------------------

_FORMS = (
    "1 + 1",
    "'text'",
    "({a: 1, b: [1, 2]})",
    "null",
    "undefined",
    "document.title",
    "document.contentType",
    "[1, 2, 3].map((x) => x * 2)",
    "(async () => { await new Promise((r) => setTimeout(r, 20)); return 'late'; })()",
    "Promise.resolve(7)",
    "Promise.reject(new Error('rejected'))",
    "() => 41 + 1",
    "async () => 'arrow'",
    "function () { return 'anonymous'; }",
    "function named() { return 'named'; }",
    "async function () { return 'async'; }",
    "  function spaced() { return 1; }  ",
    "var declared = 5",
    "let l = 6; l * 2",
    "if (true) { 'branch'; }",
    "'use strict'; (function () { return this === undefined; })()",
    "(function () { return this === undefined; })()",
    "typeof this",
    "this === globalThis",
    "throw new Error('boom')",
    "undefinedVariable",
    "let = 1 +",
    "1n + 2n",
    "typeof WebSocket",
    "typeof RTCPeerConnection",
    "1 + 1 // a trailing comment",
    # What counts as whitespace is the JavaScript engine's to say: some of these are whitespace to it and not to
    # Python's ``str.strip``, and some the other way round.
    "\ufefffunction () { return 'bom'; }",
    "\ufeffasync function () { return 'bom async'; }",
    "async\ufefffunction () { return 'between'; }",
    "function\ufeff() { return 'after keyword'; }",
    "\u0085function () { return 'nel'; }",
    "\u001cfunction () { return 'fs'; }",
    "1 + 1\u0085",
    "\u001c1 + 1\u001f",
    "\u00a0function () { return 'nbsp'; }",
    "\u2028function () { return 'line separator'; }",
)


async def _outcome(tab: Page, expression: str) -> str:
    try:
        return repr(await tab.evaluate(expression))
    except BrowserError as exc:
        return f"error: {str(exc).splitlines()[0]}"


@pytest.mark.parametrize("path", ["/", "/strict", "/trusted"])
async def test_the_script_answers_as_it_would_without_the_arm(sites: tuple[Site, Site], path: str) -> None:
    """On a plain page and on pages whose own policy forbids ``eval`` or string-to-script conversion."""
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        tab = session.get_active_page()
        differing: dict[str, tuple[str, str]] = {}
        for form in _FORMS:
            await tab.goto(inside.url(path), timeout=_TIMEOUT_MS)
            plain = await _outcome(tab, form)
            await tab.goto(inside.url(path), timeout=_TIMEOUT_MS)
            armed = await _outcome(tab, agent_world_expression(tab.context, form))
            if armed != plain:
                differing[form] = (plain, armed)

    assert differing == {}
