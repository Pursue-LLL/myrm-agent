"""The routing canary: a context with the guard's settings must really send its connections through the guard."""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.pool import EgressGuard, EgressGuardError
from tests.toolkits.browser.pool._egress_socks import admit_loopback, connect, port_of

_CANARY_HOST = "egress-guard-canary.invalid"


class FakeBrowser:
    """A browser whose pages try to load the canary name; one that honors the proxy sends the request to the guard."""

    def __init__(self, *, honors_proxy: bool) -> None:
        self._honors_proxy = honors_proxy
        self.proxy: dict[str, str] | None = None
        page = MagicMock()
        page.goto = self._goto
        self.context = MagicMock()
        self.context.new_page = AsyncMock(return_value=page)
        self.context.close = AsyncMock()

    async def new_context(self, *, proxy: dict[str, str]) -> MagicMock:
        self.proxy = proxy
        return self.context

    async def _goto(self, url: str, **_options: object) -> None:
        if self._honors_proxy and self.proxy is not None:
            _code, _reader, writer = await connect(port_of(self.proxy), _CANARY_HOST, 80)
            writer.close()
        raise TimeoutError(url)  # the name cannot load either way


def _refuse_every_lookup(host: str, _port: int) -> tuple[str, ...]:
    raise socket.gaierror(socket.EAI_NONAME, host)


class TestVerifyRouting:
    """The canary: a context with the guard's settings must really send its connections through the guard."""

    async def test_a_browser_that_routes_through_the_guard_passes_once(self) -> None:
        guard = EgressGuard(_refuse_every_lookup)
        browser = FakeBrowser(honors_proxy=True)
        try:
            await guard.verify_routing(browser)  # type: ignore[arg-type]
            await guard.verify_routing(browser)  # type: ignore[arg-type]

            assert guard.handled == 1  # the second call opened no second canary context
            browser.context.close.assert_awaited_once()
        finally:
            await guard.stop()

    async def test_the_canary_context_carries_the_guards_proxy_settings(self) -> None:
        guard = EgressGuard(_refuse_every_lookup)
        browser = FakeBrowser(honors_proxy=True)
        try:
            await guard.verify_routing(browser)  # type: ignore[arg-type]

            assert browser.proxy == await guard.start()
        finally:
            await guard.stop()

    async def test_a_browser_that_ignores_the_proxy_fails_closed(self) -> None:
        guard = EgressGuard(admit_loopback)
        browser = FakeBrowser(honors_proxy=False)
        try:
            with pytest.raises(EgressGuardError, match="did not route its connections through the egress guard"):
                await guard.verify_routing(browser)  # type: ignore[arg-type]

            browser.context.close.assert_awaited_once()
        finally:
            await guard.stop()

    async def test_a_failed_proof_is_not_remembered(self) -> None:
        guard = EgressGuard(admit_loopback)
        try:
            for _ in range(2):
                with pytest.raises(EgressGuardError):
                    await guard.verify_routing(FakeBrowser(honors_proxy=False))  # type: ignore[arg-type]
        finally:
            await guard.stop()

    async def test_a_stopped_guard_cannot_prove_anything(self) -> None:
        guard = EgressGuard(admit_loopback)
        await guard.stop()

        with pytest.raises(EgressGuardError, match="stopped"):
            await guard.verify_routing(FakeBrowser(honors_proxy=False))  # type: ignore[arg-type]
