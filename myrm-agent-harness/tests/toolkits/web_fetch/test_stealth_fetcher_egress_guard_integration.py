"""Real-Scrapling proof that the L3 stealth tier connects only through the egress guard.

Scrapling starts a Chromium of its own for every fetch, outside the browser pool, so the guard has to reach it through
Scrapling's options. The attack page of the pool tests runs against ``StealthFetcher`` with and without the guard (the
URL check is switched off, so it is not what stops the page): without it six of its requests land on the internal site
(Scrapling's resource blocking drops the image, and no name resolves without the guard), with it none does. Run with:
`pytest -m integration tests/toolkits/web_fetch/test_stealth_fetcher_egress_guard_integration.py`.
"""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.browser.pool import EgressGuard
from myrm_agent_harness.toolkits.web_fetch.fetchers.stealth_fetcher import StealthFetcher
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._egress_world import ATTACK_PATHS, PUBLIC_MARKER, REBIND_HOST, attack_world, table_resolver

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        importlib.util.find_spec("scrapling") is None or not chromium_available(),
        reason="Scrapling or Chromium not available",
    ),
]

_SHIELD = "myrm_agent_harness.toolkits.web_fetch.fetchers.stealth_fetcher.is_ssrf_shield_enabled"
_CREATE_GUARD = "myrm_agent_harness.toolkits.browser.pool.egress_guard.create_egress_guard"
# Scrapling blocks images itself, and a name is only resolved by the guard.
_REACHED_WITHOUT_GUARD = set(ATTACK_PATHS) - {"/image", "/by-name"}


@pytest.fixture(autouse=True)
def _the_url_check_is_not_what_stops_the_page() -> Iterator[None]:
    """The check judges the URL before the navigation; what is tested is the connection the browser makes."""
    with patch(_SHIELD, return_value=False):
        yield


async def _accepts(port: int) -> bool:
    try:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except ConnectionRefusedError:
        return False
    writer.close()
    return True


async def test_without_the_guard_the_attack_page_reaches_the_internal_site() -> None:
    with attack_world() as world, patch(_CREATE_GUARD, return_value=None):
        result = await StealthFetcher().fetch(world.public.url("/"))

        assert result is not None
        assert set(world.internal.paths()) >= _REACHED_WITHOUT_GUARD


async def test_through_the_guard_nothing_reaches_it_and_the_public_page_comes_back_whole() -> None:
    guard = EgressGuard(table_resolver)
    port = int((await guard.start())["server"].rsplit(":", 1)[1])
    with attack_world() as world, patch(_CREATE_GUARD, return_value=guard):
        result = await StealthFetcher().fetch(world.public_url())

        assert result is not None
        assert PUBLIC_MARKER in result.html
        assert {"/", "/own.js", "/hop"} <= set(world.public.paths())
        assert world.internal.hits == []
    assert guard.handled > 0
    assert guard.active == 0
    assert not await _accepts(port)  # the guard lived for the fetch only


@pytest.mark.parametrize("target", ["literal", "name", "redirect"])
async def test_a_document_that_leads_to_an_internal_address_is_not_fetched(target: str) -> None:
    guard = EgressGuard(table_resolver)
    with attack_world() as world, patch(_CREATE_GUARD, return_value=guard):
        url = {
            "literal": f"{world.internal_literal}/secret",
            "name": world.public_url("/secret", host=REBIND_HOST),
            "redirect": world.public_url("/hop-document"),
        }[target]

        assert await StealthFetcher().fetch(url) is None
        assert world.internal.hits == []
