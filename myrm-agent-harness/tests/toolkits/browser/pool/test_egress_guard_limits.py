"""The egress guard's limits: a resolver that hangs, more tunnels than it will serve, and a destination with several addresses.

Each must fail closed or fail small: never stall the guard, queue behind a stuck lookup, or leave a connection open.
"""

from __future__ import annotations

import asyncio
import contextlib
import resource
import socket
import threading
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.browser.pool import EgressGuard, egress_tunnel
from myrm_agent_harness.toolkits.browser.pool import egress_guard as egress_guard_module
from tests.toolkits.browser.pool._egress_socks import (
    ECHO_HOST,
    WAIT_S,
    Streams,
    admit_loopback,
    connect,
    echo_upstream,
    ends_without_a_reply,
    started,
    until,
)


class TestResolverCapacity:
    """A resolver that hangs must not stall the guard, queue connections behind it, or exhaust the process."""

    async def test_once_every_resolver_thread_is_stuck_new_connections_fail_instead_of_queuing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(egress_guard_module, "_RESOLVER_WORKERS", 2)
        monkeypatch.setattr(egress_guard_module, "_RESOLVE_TIMEOUT_S", 0.2)
        release = threading.Event()
        lookups: list[str] = []

        def resolver(host: str, _port: int) -> tuple[str, ...]:
            lookups.append(host)
            release.wait(WAIT_S)
            return ("127.0.0.1",)

        async with echo_upstream() as upstream, started(EgressGuard(resolver)) as port:
            try:
                for name in ("slow-one.test", "slow-two.test"):
                    code, _reader, writer = await connect(port, name, upstream.port)
                    writer.close()
                    assert code == 4  # the lookup outlived its timeout

                code, _reader, writer = await connect(port, "third.test", upstream.port)
                writer.close()

                assert code == 4
                assert lookups == ["slow-one.test", "slow-two.test"]  # the third never reached a thread
            finally:
                release.set()

            code = 4
            async with asyncio.timeout(WAIT_S):
                while code != 0:  # the threads return their permits shortly after the lookups are released
                    code, _reader, writer = await connect(port, "recovered.test", upstream.port)
                    writer.close()

            assert upstream.connections >= 1


class TestCapacity:
    async def test_connections_beyond_the_tunnel_cap_are_dropped_until_one_ends(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        guard = EgressGuard(admit_loopback, max_tunnels=2)
        async with echo_upstream() as upstream, started(guard) as port:
            _code, _reader, first = await connect(port, ECHO_HOST, upstream.port)
            _code, _reader, second = await connect(port, ECHO_HOST, upstream.port)
            await until(lambda: guard.active == 2)

            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"\x05\x01\x00")
            with caplog.at_level("WARNING"):
                assert await ends_without_a_reply(reader)
            writer.close()

            first.close()
            await until(lambda: guard.active == 1)
            code, _reader, third = await connect(port, ECHO_HOST, upstream.port)

            assert code == 0
            assert upstream.connections == 3
            second.close()
            third.close()
        assert caplog.text.count("Egress guard is serving its limit of 2 tunnels") == 1

    @pytest.mark.parametrize(
        ("soft_limit", "expected"),
        [
            (1024, (1024 - 64) // 3),
            (100, 16),  # a tiny limit still serves a few pages
            (1_000_000, 2048),  # a huge one does not mean thousands of tunnels
            (resource.RLIM_INFINITY, 2048),
        ],
        ids=["typical", "tiny", "huge", "unlimited"],
    )
    def test_the_default_cap_follows_the_descriptor_limit(
        self, soft_limit: int, expected: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(resource, "getrlimit", lambda _which: (soft_limit, soft_limit))

        assert egress_guard_module._default_tunnel_limit() == expected


class TestDialing:
    """``open_first``: the first address that connects wins, and nothing is left open."""

    @staticmethod
    def _dial_through(monkeypatch: pytest.MonkeyPatch, connect_to: Callable[[str, int], object]) -> None:
        monkeypatch.setattr(egress_tunnel.asyncio, "open_connection", connect_to)

    async def test_a_hanging_first_address_costs_one_stagger_not_its_connect_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_open_connection = asyncio.open_connection
        hang = asyncio.Event()

        async def open_connection(address: str, port: int) -> Streams:
            if address == "203.0.113.1":
                await hang.wait()  # never connects
            return await real_open_connection("127.0.0.1", port)

        self._dial_through(monkeypatch, open_connection)
        async with echo_upstream() as upstream:
            started_at = asyncio.get_running_loop().time()
            connection = await egress_tunnel.open_first(("203.0.113.1", "127.0.0.1"), upstream.port)
            elapsed = asyncio.get_running_loop().time() - started_at

            assert connection is not None
            assert 0.2 <= elapsed < 2.0
            connection[1].close()

    async def test_every_connection_beyond_the_first_is_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        real_open_connection = asyncio.open_connection
        released = {"192.0.2.1": asyncio.Event(), "192.0.2.2": asyncio.Event()}
        opened: list[asyncio.StreamWriter] = []

        async def open_connection(address: str, port: int) -> Streams:
            reader, writer = await real_open_connection("127.0.0.1", port)
            opened.append(writer)
            await released[address].wait()
            return reader, writer

        self._dial_through(monkeypatch, open_connection)
        async with echo_upstream() as upstream:
            dial = asyncio.ensure_future(egress_tunnel.open_first(tuple(released), upstream.port))
            await until(lambda: len(opened) == 2)  # both attempts have a socket, neither has returned
            for event in released.values():
                event.set()  # both finish in the same turn of the loop

            connection = await dial

            assert connection is not None
            assert sorted(writer.is_closing() for writer in opened) == [False, True]
            connection[1].close()

    async def test_a_dial_cancelled_by_its_deadline_cancels_every_attempt(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started_attempts: list[str] = []
        cancelled_attempts: list[str] = []

        async def open_connection(address: str, _port: int) -> Streams:
            started_attempts.append(address)
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled_attempts.append(address)
                raise
            raise AssertionError("unreachable")

        self._dial_through(monkeypatch, open_connection)
        dial = asyncio.ensure_future(egress_tunnel.open_first(("192.0.2.1", "192.0.2.2"), 80))
        await until(lambda: len(started_attempts) == 2)

        dial.cancel()
        with pytest.raises(asyncio.CancelledError):
            await dial

        assert sorted(cancelled_attempts) == ["192.0.2.1", "192.0.2.2"]

    async def test_no_address_connecting_is_none(self) -> None:
        with contextlib.closing(socket.socket()) as probe:
            probe.bind(("127.0.0.1", 0))
            dead_port = probe.getsockname()[1]

        assert await egress_tunnel.open_first(("127.0.0.1", "::1"), dead_port) is None

    async def test_only_a_bounded_number_of_addresses_is_tried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        tried: list[str] = []

        async def open_connection(address: str, _port: int) -> Streams:
            tried.append(address)
            raise ConnectionRefusedError(address)

        self._dial_through(monkeypatch, open_connection)

        assert await egress_tunnel.open_first(tuple(f"192.0.2.{n}" for n in range(1, 21)), 80) is None
        assert len(tried) == egress_tunnel._MAX_DIAL_ADDRESSES
