"""Egress guard: a loopback SOCKS5 proxy that lets a browser connect only to addresses the SSRF policy admits.

[INPUT]
- .egress_policy::Resolver, EgressRefusedError, resolve_public_addresses, environment_proxy_configured (POS: what a browser may connect to, and where the policy cannot apply)
- core.security.http.secure_fetch::is_ssrf_shield_enabled (POS: the operator's switch for the SSRF policy)
- .egress_tunnel::read_connect_request, open_first, relay, reply, close_writer (POS: SOCKS5 parsing, dialing and the byte relay)
- patchright.async_api::Browser, ProxySettings (POS: the browser a context is created in, and the proxy option a context takes)

[OUTPUT]
- EgressGuard: the proxy; ``start`` returns the proxy settings of a context, ``verify_routing`` proves a browser honors them, ``stop`` ends it
- create_egress_guard: a guard for this process's browsers, or None where the policy cannot apply
- EgressGuardError: a browser that does not route through the guard, or a guard that was stopped

[POS]
Closes the gap between checking a URL and connecting to it for the browser tiers. A URL check resolves the host
name, but Chromium resolves it again when it connects: a name that answers the check with a public address and the
browser with an internal one (DNS rebinding, ``169.254.169.254.nip.io``) reaches internal services, and a redirect
hop, a subresource or a script-started request is only ever judged by its literal host. Over SOCKS5 Chromium hands the
host *name* to the proxy, so the guard resolves it once, requires every answer to pass the policy, and dials only
those addresses: the address that was judged is the address that is connected. The page cannot opt out, whatever
starts the request, and a name that does not resolve to a public address fails as an ordinary connection error.

The guard is a single point: when it stops or cannot be reached the browser has no network, which is the safe failure,
and it is never restarted (a restart changes the port, which a created context cannot follow). It does not chain to an
upstream proxy: where the environment forces one (``environment_proxy_configured``) the proxy's operator owns the
egress policy and the guard is not used. Name resolution runs on the guard's own threads, tunnels are capped by the
process's descriptor limit, and every wait is bounded, so neither a slow resolver nor a flood of connections can stall
the event loop or exhaust the process.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.http.secure_fetch import is_ssrf_shield_enabled

from .egress_policy import EgressRefusedError, Resolver, environment_proxy_configured, resolve_public_addresses
from .egress_tunnel import (
    REPLY_FAILURE,
    REPLY_HOST_UNREACHABLE,
    REPLY_NOT_ALLOWED,
    REPLY_OK,
    RefusedRequestError,
    close_writer,
    open_first,
    read_connect_request,
    relay,
    reply,
)

if TYPE_CHECKING:
    from patchright.async_api import Browser, ProxySettings

logger = logging.getLogger(__name__)

_IDLE_TIMEOUT_S = 300.0  # silence in both directions that ends a tunnel (a peer that vanished without a FIN)
_HANDSHAKE_TIMEOUT_S = 10.0
_RESOLVE_TIMEOUT_S = 5.0
_DIAL_DEADLINE_S = 10.0  # one budget for all addresses of a host
_RESOLVER_WORKERS = 8
_STOP_TIMEOUT_S = 2.0
_BACKLOG = 1024

# A tunnel holds two descriptors, a third while a second address is being dialed; the rest is the process's own.
_FDS_PER_TUNNEL = 3
_FD_RESERVE = 64
_MIN_TUNNELS = 16
_MAX_TUNNELS = 2048
_FALLBACK_TUNNELS = 256

# Chromium never proxies loopback unless told to; ``<-loopback>`` takes the implicit bypass away, so 127.0.0.1 and
# localhost reach the guard like every other destination.
_PROXY_BYPASS = "<-loopback>"
# A name that cannot exist (RFC 6761): the canary never reaches a real host, whatever a resolver answers.
_CANARY_URL = "http://egress-guard-canary.invalid/"
_CANARY_TIMEOUT_MS = 5000


class EgressGuardError(RuntimeError):
    """The browser cannot be kept behind the egress guard."""


class _ResolverBusyError(OSError):
    """Every resolver thread is occupied; the connection fails instead of queuing behind a stuck lookup."""


def _default_tunnel_limit() -> int:
    """The tunnel cap the process's descriptor limit allows."""
    try:
        import resource
    except ImportError:  # Windows has no descriptor limit to read
        return _FALLBACK_TUNNELS
    soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft == resource.RLIM_INFINITY:
        return _MAX_TUNNELS
    return max(_MIN_TUNNELS, min(_MAX_TUNNELS, (soft - _FD_RESERVE) // _FDS_PER_TUNNEL))


class EgressGuard:
    """A loopback SOCKS5 proxy that dials only addresses its resolver returned.

    One guard serves every context of a pool. It listens on an ephemeral port of 127.0.0.1, starts on first use and
    stops for good with ``stop``.
    """

    def __init__(
        self,
        resolver: Resolver = resolve_public_addresses,
        *,
        idle_timeout_s: float = _IDLE_TIMEOUT_S,
        max_tunnels: int | None = None,
    ) -> None:
        """
        Args:
            resolver: Decides which addresses a destination may be dialed at; the cloud SSRF policy by default.
            idle_timeout_s: Silence in both directions after which a tunnel is closed.
            max_tunnels: Concurrent connections served; derived from the descriptor limit when None.
        """
        self._resolver = resolver
        self._idle_timeout_s = idle_timeout_s
        self._max_tunnels = max_tunnels if max_tunnels is not None else _default_tunnel_limit()
        self._server: asyncio.Server | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._port = 0
        self._stopped = False
        self._tunnels: set[asyncio.Task[None]] = set()
        self._saturated = False
        self._handled = 0
        self._verified = False
        self._start_lock = asyncio.Lock()
        self._verify_lock = asyncio.Lock()
        self._resolver_pool: ThreadPoolExecutor | None = None
        self._resolver_slots = threading.BoundedSemaphore(_RESOLVER_WORKERS)

    @property
    def handled(self) -> int:
        """SOCKS5 requests read so far, whatever their outcome."""
        return self._handled

    @property
    def active(self) -> int:
        """Connections being served."""
        return len(self._tunnels)

    async def start(self) -> ProxySettings:
        """Start listening (the first call only) and return the proxy settings a browser context must be created with.

        Raises:
            EgressGuardError: the guard was stopped.
        """
        async with self._start_lock:
            if self._stopped:
                raise EgressGuardError("The egress guard was stopped and is not restarted")
            if self._server is None:
                self._loop = asyncio.get_running_loop()
                self._resolver_pool = ThreadPoolExecutor(max_workers=_RESOLVER_WORKERS, thread_name_prefix="egress-dns")
                self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0, backlog=_BACKLOG)
                self._port = self._server.sockets[0].getsockname()[1]
                logger.info(
                    "Egress guard listening on 127.0.0.1:%d (at most %d tunnels)", self._port, self._max_tunnels
                )
        return {"server": f"socks5://127.0.0.1:{self._port}", "bypass": _PROXY_BYPASS}

    async def stop(self) -> None:
        """Refuse new connections and end the ones being served; the guard cannot be started again.

        Never raises: exit hooks stop it on a private event loop, after the loop that owns the listener has closed.
        """
        self._stopped = True
        server, self._server = self._server, None
        pool, self._resolver_pool = self._resolver_pool, None
        tunnels = list(self._tunnels)
        if server is not None:
            with contextlib.suppress(RuntimeError):  # the owning loop is closed
                server.close()
        for task in tunnels:
            with contextlib.suppress(RuntimeError):
                task.cancel()
        if tunnels and self._loop is asyncio.get_running_loop():  # tasks of another loop cannot be awaited from here
            await asyncio.wait(tunnels, timeout=_STOP_TIMEOUT_S)
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    async def verify_routing(self, browser: Browser) -> None:
        """Prove that a context created with this guard's settings really connects through it (once per guard).

        A context that accepts the proxy option but does not use it (a browser whose per-context proxy is unsupported,
        a launch flag that overrides it) would send every connection around the guard with no sign of it. A page is
        opened on a name that cannot exist: when the guard is in the path it hears of the request, whatever happens to
        the page afterwards.

        Raises:
            EgressGuardError: the guard heard nothing of the request, or was stopped.
        """
        if self._verified:
            return
        settings = await self.start()
        async with self._verify_lock:
            if self._verified:
                return
            before = self._handled
            context = await browser.new_context(proxy=settings)
            try:
                page = await context.new_page()
                with contextlib.suppress(Exception):  # the name cannot load; only whether the guard heard of it counts
                    await page.goto(_CANARY_URL, timeout=_CANARY_TIMEOUT_MS)
            finally:
                with contextlib.suppress(Exception):
                    await context.close()
            if self._handled == before:
                raise EgressGuardError(
                    "The browser did not route its connections through the egress guard; "
                    "refusing to open pages without connection-level network isolation"
                )
            self._verified = True

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """One accepted connection: tracked so ``stop`` can end it, its client socket closed whatever happens."""
        task = asyncio.current_task()
        if task is not None:
            self._tunnels.add(task)
        try:
            await self._tunnel(reader, writer)
        except (asyncio.IncompleteReadError, OSError):
            pass  # the browser went away, or sent something that is no SOCKS5 request
        finally:
            close_writer(writer)
            if task is not None:
                self._tunnels.discard(task)

    async def _tunnel(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Serve one connection: read its CONNECT request, judge the destination, dial it, relay until either side ends."""
        if self._server is None:
            return  # accepted while stopping
        if len(self._tunnels) > self._max_tunnels:
            if not self._saturated:
                self._saturated = True
                logger.warning(
                    "Egress guard is serving its limit of %d tunnels; new connections are dropped", self._max_tunnels
                )
            return
        self._saturated = False
        try:
            async with asyncio.timeout(_HANDSHAKE_TIMEOUT_S):
                host, port = await read_connect_request(reader, writer)
        except RefusedRequestError as refusal:
            await reply(writer, refusal.code)
            return
        self._handled += 1
        addresses = await self._admitted_addresses(host, port, writer)
        if addresses is None:
            return
        try:
            async with asyncio.timeout(_DIAL_DEADLINE_S):
                upstream = await open_first(addresses, port)
        except TimeoutError:
            upstream = None
        if upstream is None:
            await reply(writer, REPLY_HOST_UNREACHABLE)
            return
        try:
            await reply(writer, REPLY_OK)
            await relay((reader, writer), upstream, self._idle_timeout_s)
        finally:
            close_writer(upstream[1])

    async def _admitted_addresses(self, host: str, port: int, writer: asyncio.StreamWriter) -> tuple[str, ...] | None:
        """The addresses ``host`` may be dialed at, or None after the browser was told why not."""
        try:
            return await self._resolve(host, port)
        except EgressRefusedError as refusal:
            logger.warning("Egress guard refused %s:%d: %s", host, port, refusal)
            code = REPLY_NOT_ALLOWED
        except OSError as failure:  # unresolvable, resolver timeout or resolver capacity
            logger.debug("Egress guard could not resolve %s:%d: %r", host, port, failure)
            code = REPLY_HOST_UNREACHABLE
        except Exception:
            logger.exception("Egress resolver failed for %s:%d", host, port)
            code = REPLY_FAILURE
        await reply(writer, code)
        return None

    async def _resolve(self, host: str, port: int) -> tuple[str, ...]:
        """Run the resolver on the guard's own threads, so a slow lookup cannot starve the event loop or other work.

        A lookup that outlives its timeout keeps its thread until it returns; the permit is held until then, and once
        every thread is taken new connections fail instead of queuing behind lookups that may themselves be stuck.
        """
        if self._resolver_pool is None or not self._resolver_slots.acquire(blocking=False):
            raise _ResolverBusyError("no resolver thread is free")

        def lookup() -> tuple[str, ...]:
            try:
                return tuple(self._resolver(host, port))
            finally:
                self._resolver_slots.release()

        try:
            pending = asyncio.get_running_loop().run_in_executor(self._resolver_pool, lookup)
        except BaseException:
            self._resolver_slots.release()
            raise
        return await asyncio.wait_for(pending, _RESOLVE_TIMEOUT_S)


@functools.cache
def _warn_environment_proxy() -> None:
    logger.warning(
        "Browser egress guard not used: the environment routes HTTP traffic through a proxy, "
        "so the proxy's operator must enforce the egress policy"
    )


def create_egress_guard() -> EgressGuard | None:
    """A guard for the browsers of this process, or ``None`` where the policy cannot apply.

    ``None`` when the SSRF shield is off (there is no policy to enforce), and when the environment sends the process's
    HTTP traffic through a proxy of its own: the guard dials directly, so it would route around that proxy.
    """
    if not is_ssrf_shield_enabled():
        return None
    if environment_proxy_configured():
        _warn_environment_proxy()
        return None
    return EgressGuard()
