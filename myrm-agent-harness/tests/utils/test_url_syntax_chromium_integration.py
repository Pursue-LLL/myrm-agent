"""Real Chromium dials the host a canonical URL names.

A URL is judged and dialed in its canonical spelling (``utils.url_syntax``), so the host a policy classifies is the host
a client connects to only if the client reads that spelling the way the canonicalizer does. Chromium is asked about every
spelling in ``DIAL_SPELLINGS``: its resolver connects every name to the loopback listener, so the Host header the
listener receives is the host Chromium derived from the URL. The same spellings are also dialed as written, which shows
where a hop that is still dialed as written would be read differently. Run with:
`pytest -m integration tests/utils/test_url_syntax_chromium_integration.py`.
"""

from __future__ import annotations

import pytest
from patchright.async_api import Error as PatchrightError
from patchright.async_api import Page, async_playwright

from myrm_agent_harness.utils.url_syntax import parse_outbound_url
from tests.support.dial_probe import (
    KEEPS_THE_TRAILING_DOT,
    REFUSES_IT,
    Dial,
    HostRecorder,
    Sent,
    host_recorder,
    misdialed_canonical_urls,
    readings_that_differ,
)
from tests.support.host_spellings import DIAL_SPELLINGS
from tests.toolkits.browser._browser_available import chromium_available

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_GOTO_TIMEOUT_MS = 4_000
_LAUNCH_ARGS = ["--host-resolver-rules=MAP * 127.0.0.1", "--no-proxy-server"]

# Where Chromium reads a spelling as written differently from the canonicalizer; every other spelling is the same host.
_DIFFERENT_AS_WRITTEN = {
    "example.test.": KEEPS_THE_TRAILING_DOT,
    "Example.Test.": KEEPS_THE_TRAILING_DOT,
    "localhost.": KEEPS_THE_TRAILING_DOT,
    "\u200d.test": REFUSES_IT,
    "a\u200db.test": REFUSES_IT,
    "a\u200cb.test": REFUSES_IT,
    "٣.test": REFUSES_IT,
    "a.٣": REFUSES_IT,
    "[example.test]": REFUSES_IT,
    "[v1.x]": REFUSES_IT,
}


async def _dial(page: Page, recorder: HostRecorder, url: str, path: str) -> Sent:
    try:
        await page.goto(url, timeout=_GOTO_TIMEOUT_MS)
    except PatchrightError as error:
        if "invalid URL" in str(error):
            return Sent(refused=True)
        raise
    return Sent(recorder.host_sent(path))


@pytest.fixture(scope="module")
async def dials() -> list[Dial]:
    results: list[Dial] = []
    with host_recorder() as recorder:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            try:
                page = await browser.new_page()
                for index, spelling in enumerate(DIAL_SPELLINGS):
                    target, error = parse_outbound_url(f"http://{spelling}:{recorder.port}/c{index}")
                    assert target is not None, f"{spelling!r} has no canonical spelling ({error}): drop it"
                    results.append(
                        Dial(
                            spelling,
                            target.hostname,
                            await _dial(page, recorder, target.url, f"/c{index}"),
                            await _dial(page, recorder, f"http://{spelling}:{recorder.port}/w{index}", f"/w{index}"),
                        )
                    )
            finally:
                await browser.close()
    return results


def test_chromium_dials_the_canonical_host_of_every_canonical_url(dials: list[Dial]) -> None:
    assert len(dials) == len(DIAL_SPELLINGS)
    assert misdialed_canonical_urls(dials) == {}


def test_chromium_reads_a_spelling_as_written_the_way_the_canonicalizer_does_except_where_declared(
    dials: list[Dial],
) -> None:
    assert readings_that_differ(dials) == _DIFFERENT_AS_WRITTEN
