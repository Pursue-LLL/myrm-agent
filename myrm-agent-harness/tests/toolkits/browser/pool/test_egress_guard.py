"""The egress guard as a SOCKS5 proxy: what it answers, what it refuses, and how it starts and stops, with no browser involved.

A raw SOCKS5 client plays the browser and a loopback echo server plays the destination (see ``_egress_socks``). The policy that
decides what is admitted is a function the test passes in.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import threading

import pytest

from myrm_agent_harness.toolkits.browser.pool import EgressGuard, EgressGuardError
from myrm_agent_harness.toolkits.browser.pool import egress_guard as egress_guard_module
from myrm_agent_harness.toolkits.browser.pool.egress_policy import EgressRefusedError
from tests.toolkits.browser.pool._egress_socks import (
    ECHO_HOST,
    WAIT_S,
    admit_loopback,
    connect,
    echo_upstream,
    port_of,
    started,
    until,
)


class TestTunnel:
    async def test_an_admitted_destination_is_dialed_and_bytes_flow_both_ways(self) -> None:
        async with echo_upstream() as upstream, started(EgressGuard(admit_loopback)) as port:
            code, reader, writer = await connect(port, ECHO_HOST, upstream.port)
            writer.write(b"ping")

            assert code == 0
            assert await asyncio.wait_for(reader.readexactly(4), WAIT_S) == b"ping"
            assert upstream.connections == 1
            writer.close()

    async def test_the_resolver_is_asked_once_per_connection_with_the_destination_as_sent(self) -> None:
        asked: list[tuple[str, int]] = []

        def resolver(host: str, resolved_port: int) -> tuple[str, ...]:
            asked.append((host, resolved_port))
            return ("127.0.0.1",)

        async with echo_upstream() as upstream, started(EgressGuard(resolver)) as port:
            _code, _reader, writer = await connect(port, "Echo.Test", upstream.port)
            writer.close()

            assert asked == [("Echo.Test", upstream.port)]

    async def test_a_half_close_reaches_the_destination_and_the_answer_still_comes_back(self) -> None:
        async with echo_upstream() as upstream, started(EgressGuard(admit_loopback)) as port:
            _code, reader, writer = await connect(port, ECHO_HOST, upstream.port)
            writer.write(b"request")
            writer.write_eof()

            assert await asyncio.wait_for(reader.read(), WAIT_S) == b"request"  # then the end of the stream
            writer.close()

    async def test_a_tunnel_ends_when_the_browser_hangs_up(self) -> None:
        guard = EgressGuard(admit_loopback)
        async with echo_upstream() as upstream, started(guard) as port:
            _code, _reader, writer = await connect(port, ECHO_HOST, upstream.port)
            await until(lambda: guard.active == 1)

            writer.close()

            await until(lambda: guard.active == 0)

    async def test_a_silent_tunnel_is_closed_after_the_idle_timeout(self) -> None:
        guard = EgressGuard(admit_loopback, idle_timeout_s=0.2)
        async with echo_upstream() as upstream, started(guard) as port:
            _code, reader, writer = await connect(port, ECHO_HOST, upstream.port)

            assert await asyncio.wait_for(reader.read(1), WAIT_S) == b""
            await until(lambda: guard.active == 0)
            writer.close()

    async def test_the_second_address_is_used_when_the_first_refuses(self) -> None:
        def resolver(_host: str, _port: int) -> tuple[str, ...]:
            return ("::1", "127.0.0.1")  # nothing listens on the IPv6 loopback port, so the first attempt is refused

        async with echo_upstream() as upstream, started(EgressGuard(resolver)) as port:
            code, reader, writer = await connect(port, ECHO_HOST, upstream.port)
            writer.write(b"ok")

            assert code == 0
            assert await asyncio.wait_for(reader.readexactly(2), WAIT_S) == b"ok"
            writer.close()

    async def test_the_resolver_runs_on_a_worker_thread_not_on_the_event_loop(self) -> None:
        loop_thread = threading.get_ident()
        seen: list[int] = []

        def resolver(_host: str, _port: int) -> tuple[str, ...]:
            seen.append(threading.get_ident())
            return ("127.0.0.1",)

        async with echo_upstream() as upstream, started(EgressGuard(resolver)) as port:
            _code, _reader, writer = await connect(port, ECHO_HOST, upstream.port)
            writer.close()

        assert seen
        assert loop_thread not in seen


class TestRefusals:
    async def test_a_refused_destination_gets_not_allowed_and_is_never_dialed(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        def resolver(host: str, _port: int) -> tuple[str, ...]:
            raise EgressRefusedError(f"{host} is internal")

        async with echo_upstream() as upstream, started(EgressGuard(resolver)) as port:
            with caplog.at_level("WARNING"):
                code, reader, _writer = await connect(port, ECHO_HOST, upstream.port)

            assert code == 2
            assert await asyncio.wait_for(reader.read(), WAIT_S) == b""
            assert upstream.connections == 0
        assert f"Egress guard refused {ECHO_HOST}:{upstream.port}: {ECHO_HOST} is internal" in caplog.text

    async def test_the_default_policy_refuses_every_literal_internal_destination(self) -> None:
        async with echo_upstream() as upstream, started(EgressGuard()) as port:
            for host in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "169.254.169.254", "10.1.2.3", "localhost"):
                code, _reader, writer = await connect(port, host, upstream.port)
                writer.close()

                assert code == 2, host
            assert upstream.connections == 0

    async def test_a_name_that_does_not_resolve_gets_host_unreachable(self) -> None:
        def resolver(host: str, _port: int) -> tuple[str, ...]:
            raise socket.gaierror(socket.EAI_NONAME, host)

        async with started(EgressGuard(resolver)) as port:
            code, _reader, writer = await connect(port, "gone.test", 80)
            writer.close()

            assert code == 4

    async def test_a_resolver_that_crashes_gets_general_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        def resolver(_host: str, _port: int) -> tuple[str, ...]:
            raise RuntimeError("resolver bug")

        async with started(EgressGuard(resolver)) as port:
            with caplog.at_level("ERROR"):
                code, _reader, writer = await connect(port, "any.test", 80)
            writer.close()

            assert code == 1
        assert "Egress resolver failed for any.test:80" in caplog.text

    async def test_an_address_nothing_listens_at_gets_host_unreachable(self) -> None:
        with contextlib.closing(socket.socket()) as probe:
            probe.bind(("127.0.0.1", 0))
            dead_port = probe.getsockname()[1]

        async with started(EgressGuard(admit_loopback)) as port:
            code, _reader, writer = await connect(port, ECHO_HOST, dead_port)
            writer.close()

            assert code == 4

    @pytest.mark.parametrize("command", [2, 3], ids=["bind", "udp-associate"])
    async def test_a_command_other_than_connect_gets_command_not_supported(self, command: int) -> None:
        guard = EgressGuard(admit_loopback)
        async with started(guard) as port:
            code, _reader, writer = await connect(port, ECHO_HOST, 80, command=command)
            writer.close()

            assert code == 7
            assert guard.handled == 0

    async def test_an_unknown_address_type_gets_address_type_not_supported(self) -> None:
        async with started(EgressGuard(admit_loopback)) as port:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"\x05\x01\x00")
            await reader.readexactly(2)
            writer.write(bytes([5, 1, 0, 9]) + b"\x00" * 8)

            assert (await reader.readexactly(10))[1] == 8
            writer.close()

    @pytest.mark.parametrize(
        ("greeting", "answer"),
        [
            (b"GET /" + b" " * 95, b""),
            (b"\x04\x01\x00\x50\x7f\x00\x00\x01\x00", b""),
            (b"\x05\x01\x02", b"\x05\xff"),  # SOCKS5, but only with a user name and password
        ],
        ids=["http", "socks4", "authentication"],
    )
    async def test_a_peer_that_does_not_speak_unauthenticated_socks5_is_dropped(
        self, greeting: bytes, answer: bytes
    ) -> None:
        guard = EgressGuard(admit_loopback)
        async with started(guard) as port:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(greeting)

            assert await asyncio.wait_for(reader.read(), WAIT_S) == answer
            assert guard.handled == 0
            writer.close()

    async def test_a_peer_that_never_sends_a_request_is_dropped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(egress_guard_module, "_HANDSHAKE_TIMEOUT_S", 0.2)
        async with started(EgressGuard(admit_loopback)) as port:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)

            assert await asyncio.wait_for(reader.read(), WAIT_S) == b""
            writer.close()


class TestLifecycle:
    async def test_stop_ends_the_tunnels_and_refuses_new_connections(self) -> None:
        guard = EgressGuard(admit_loopback)
        async with echo_upstream() as upstream:
            port = port_of(await guard.start())
            _code, reader, _writer = await connect(port, ECHO_HOST, upstream.port)
            await until(lambda: guard.active == 1)

            await guard.stop()

            assert await asyncio.wait_for(reader.read(), WAIT_S) == b""
            assert guard.active == 0
            with pytest.raises(ConnectionRefusedError):
                await asyncio.open_connection("127.0.0.1", port)

    async def test_a_stopped_guard_is_never_restarted(self) -> None:
        guard = EgressGuard(admit_loopback)
        await guard.start()
        await guard.stop()

        with pytest.raises(EgressGuardError, match="stopped"):
            await guard.start()

    async def test_stop_is_safe_before_start_and_when_repeated(self) -> None:
        guard = EgressGuard(admit_loopback)
        await guard.stop()
        await guard.stop()

        with pytest.raises(EgressGuardError):
            await guard.start()

    async def test_start_is_idempotent_and_returns_the_settings_of_one_listener(self) -> None:
        guard = EgressGuard(admit_loopback)
        try:
            first, second = await asyncio.gather(guard.start(), guard.start())

            assert first == second
            assert first["server"].startswith("socks5://127.0.0.1:")
            assert first["bypass"] == "<-loopback>"
        finally:
            await guard.stop()

    async def test_the_listener_is_bound_to_the_loopback_interface_only(self) -> None:
        guard = EgressGuard(admit_loopback)
        try:
            await guard.start()
            server = guard._server

            assert server is not None
            assert [sock.getsockname()[0] for sock in server.sockets] == ["127.0.0.1"]
        finally:
            await guard.stop()
