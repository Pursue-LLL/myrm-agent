"""Real-Chromium proof that the allowlist's policy holds in documents with no head and in a page that rewrites its head.

The policy is a ``<meta>`` in the head of the document, and some documents have none when their script first runs: an
SVG or an XML document is a tree with no head, and an XHTML document may run a script before its parser has built the
head. The script of Layer 0 gives such a document a head just before a page script or the agent's own JavaScript opens a
WebSocket, a channel no request filter sees. A page can also rewrite its own head (remove the policy ``<meta>``, remove
the head, empty it, or rewrite the whole document): the browser keeps enforcing the policy it applied, the agent's next
script still runs, and the document holds exactly one policy ``<meta>``. A second loopback server records every request
it receives, so a WebSocket that reaches outside shows up there. Run with:
`pytest -m integration tests/toolkits/browser/test_policy_document_kinds_integration.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from myrm_agent_harness.toolkits.browser.session.extractor import Extractor
from tests.toolkits.browser._allowlisted_session import allowlisted_session
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._channel_probe import probe_expression
from tests.toolkits.browser._redirect_servers import Reply, Site, page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_SETTLE_S = 0.6  # a WebSocket handshake to a loopback server needs far less to be seen there
_XHTML = "http://www.w3.org/1999/xhtml"
_POLICY_COUNT = "document.querySelectorAll('meta[http-equiv]').length"
_REWRITES = {
    "removes the policy meta": "document.querySelectorAll('meta[http-equiv]').forEach(m => m.remove())",
    "removes the head": "document.head.remove()",
    "empties the head": "document.head.innerHTML = ''",
    "rewrites the document": "document.open(); document.write('<p>x</p>'); document.close();",
}


def _xhtml(inner: str) -> Reply:
    return Reply(body=f'<html xmlns="{_XHTML}">{inner}</html>'.encode(), content_type="application/xhtml+xml")


def _documents(leak: str) -> dict[str, Reply]:
    """Documents with no head when their script runs, which open a WebSocket to ``leak`` from it; and a quiet one."""
    script = f"new WebSocket('{leak}');"

    def xml(root: str, content_type: str) -> Reply:
        body = f'<?xml version="1.0"?><{root} xmlns:h="{_XHTML}"><h:script>{script}</h:script></{root}>'
        return Reply(body=body.encode(), content_type=content_type)

    return {
        "/": page("home"),
        "/xml": xml("root", "application/xml"),
        "/text-xml": xml("root", "text/xml"),
        "/rss": xml("rss", "application/rss+xml"),
        "/svg": Reply(
            body=f'<svg xmlns="http://www.w3.org/2000/svg"><script>{script}</script></svg>'.encode(),
            content_type="image/svg+xml",
        ),
        "/xhtml-no-head": _xhtml(f"<body><script>{script}</script></body>"),
        "/xhtml-script-before-head": _xhtml(f"<script>{script}</script><head><title>kept</title></head><body>b</body>"),
        "/xhtml-quiet": _xhtml("<body><p>read me</p></body>"),
    }


_SCRIPTED = ("/xml", "/text-xml", "/rss", "/svg", "/xhtml-no-head", "/xhtml-script-before-head")


def _leak_url(outside: Site) -> str:
    """A WebSocket URL on the outside server; ``localhost`` is not on the allowlist, which holds ``127.0.0.1``."""
    return outside.base_url.replace("127.0.0.1", "localhost").replace("http", "ws") + "/leak"


@pytest.fixture
def sites() -> Iterator[tuple[Site, Site]]:
    """The allowlisted site, whose documents try to reach the second server, which the allowlist keeps out."""
    with serve({"/": page("outside")}) as outside, serve(_documents(_leak_url(outside))) as inside:
        yield inside, outside


async def test_a_page_script_cannot_reach_outside_the_allowlist_from_a_document_with_no_head_when_it_runs(
    sites: tuple[Site, Site],
) -> None:
    inside, outside = sites
    leaked: dict[str, int] = {}
    async with allowlisted_session(inside) as session:
        for path in _SCRIPTED:
            before = len(outside.hits)
            await session.navigate(inside.url(path))
            await asyncio.sleep(_SETTLE_S)
            if len(outside.hits) > before:
                leaked[path] = len(outside.hits) - before

    assert leaked == {}


async def test_the_agents_script_is_judged_in_a_document_with_no_head_as_it_is_in_a_page(
    sites: tuple[Site, Site],
) -> None:
    inside, outside = sites
    probe = probe_expression("direct", outside.base_url.replace("127.0.0.1", "localhost"), inside.base_url)
    async with allowlisted_session(inside) as session:
        await session.navigate(inside.url("/"))
        in_a_page = await session.evaluate(probe)
        verdicts = {}
        for path in _SCRIPTED:
            await session.navigate(inside.url(path))
            verdicts[path] = await session.evaluate(probe)

    assert verdicts == dict.fromkeys(_SCRIPTED, in_a_page)


async def test_the_page_and_the_agent_share_the_one_head_whichever_of_them_made_it(sites: tuple[Site, Site]) -> None:
    """The page's script made the head when it opened its WebSocket; the agent's script finds it and adds nothing."""
    inside, _ = sites
    counts = f"[document.documentElement.getElementsByTagNameNS('{_XHTML}', 'head').length, {_POLICY_COUNT}].join()"
    async with allowlisted_session(inside) as session:
        for path in ("/xml", "/svg", "/xhtml-no-head"):
            await session.navigate(inside.url(path))
            await asyncio.sleep(_SETTLE_S)
            assert await session.evaluate("1 + 1") == "2", path
            assert await session.evaluate(counts) == "1,1", path


async def test_the_head_the_policy_adds_leaves_what_the_page_reads_as_it_was(sites: tuple[Site, Site]) -> None:
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        await session.navigate(inside.url("/xhtml-quiet"))
        extractor = Extractor(session.get_active_page())
        before = await extractor.extract_full_text()
        assert await session.evaluate(_POLICY_COUNT) == "1"
        assert await extractor.extract_full_text() == before == "read me"


async def test_a_head_the_parser_builds_after_the_policy_head_costs_the_document_neither_title_nor_policy(
    sites: tuple[Site, Site],
) -> None:
    inside, _ = sites
    async with allowlisted_session(inside) as session:
        await session.navigate(inside.url("/xhtml-script-before-head"))
        assert await session.evaluate("document.title") == "kept"
        assert await session.evaluate("document.head.querySelectorAll('meta[http-equiv]').length") == "1"


async def test_a_page_that_rewrites_its_head_keeps_one_policy_and_the_agents_script_keeps_running(
    sites: tuple[Site, Site],
) -> None:
    """Each rewrite, made before and after the agent's first script: that script still runs and no WebSocket leaks."""
    inside, outside = sites
    reach_outside = f"new WebSocket('{_leak_url(outside)}'); 1 + 1"
    counts = f"[document.querySelectorAll('head').length, {_POLICY_COUNT}].join()"
    async with allowlisted_session(inside) as session:
        tab = session.get_active_page()
        for agent_ran_first in (False, True):
            for rewrite, script in _REWRITES.items():
                where = f"page {rewrite}, agent's script ran first: {agent_ran_first}"
                await session.navigate(inside.url("/"))
                if agent_ran_first:
                    assert await session.evaluate("1 + 1") == "2", where
                await tab.evaluate(script)
                hits = len(outside.hits)
                assert await session.evaluate(reach_outside) == "2", where
                await asyncio.sleep(_SETTLE_S)
                assert await session.evaluate(counts) == "1,1", where
                assert len(outside.hits) == hits, where
