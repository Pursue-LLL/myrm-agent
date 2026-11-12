"""Lazily mounted API route groups.

[INPUT]
- fastapi.APIRouter (POS: the aggregate router each group's routers are included into)
- starlette.types (POS: ASGI contracts of the request middleware)

[OUTPUT]
- RouterMount: one router mount, declared as data
- LazyRouteLoader: the aggregate router; imports a route group the first time a request needs it
- LazyRouteMiddleware: loads the group a request path belongs to before the router matches it
- segment_of_path: the route group a request path belongs to

[POS]
The routers are most of the server's import graph, yet a launch only needs the few endpoints its first requests hit.
A ``RouterMount`` declares an ``include_router`` call as data; the module behind it is imported when a request targets
its group (the first path segment below the API prefix) or when ``LazyRouteLoader.preload`` reaches it. A request
attaches its own group at once; the groups ``preload`` imported are attached together when it is done. Every attach
invalidates FastAPI's cached route table and the next request rebuilds the table of everything attached so far, so
attaching the groups one request apart costs seconds of loop time where one batch costs a single rebuild. A router is
included into the aggregate with the mount's prefix and tags, at the mount's declaration position. Once every group is
attached the aggregate is the one an eager ``include_router`` sequence builds: same structure, same route order, same
OpenAPI output.
Groups are imported synchronously on the calling thread (the event loop in the server): all modules of a group first,
its routers attached afterwards, so a failed import leaves the group unmounted for the next request to retry.
A group's mounts must serve only paths below its segment: a request is routed to the group its first path segment names.
"""

from __future__ import annotations

import asyncio
import bisect
import contextlib
import logging
import threading
import time
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from importlib import import_module

from fastapi import APIRouter
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# While preloading, the loop idles this long per second of import work: it stays free for requests at least half of the time
# (back-to-back imports leave a request one loop turn per group).
PRELOAD_IDLE_RATIO = 1.0


@dataclass(frozen=True, slots=True)
class RouterMount:
    """One ``include_router`` call, declared as data so its module is imported only when its group loads."""

    segment: str
    module: str
    attr: str = "router"
    prefix: str = ""
    tags: tuple[str, ...] = ()
    factory: bool = False
    local_only: bool = False

    def resolve(self) -> APIRouter:
        """Import the module and return the router it exposes (``attr`` is a zero-argument factory when ``factory``)."""
        target: object = getattr(import_module(self.module), self.attr)
        router = target() if self.factory and callable(target) else target
        if not isinstance(router, APIRouter):
            raise TypeError(f"{self.module}.{self.attr} is not an APIRouter")
        return router


@dataclass(frozen=True, slots=True)
class AttachedRouter:
    """A router just included into the aggregate, with the prefix of its include."""

    router: APIRouter
    prefix: str


@dataclass(slots=True)
class _Group:
    mounts: list[tuple[int, RouterMount]] = field(default_factory=list)
    routers: list[APIRouter] | None = None  # imported, in ``mounts`` order
    loaded: bool = False  # attached to the aggregate


AttachListener = Callable[[Sequence[AttachedRouter]], None]


class LazyRouteLoader:
    """The API aggregate router (``router``) whose route groups are imported on first use."""

    def __init__(
        self,
        mounts: Iterable[RouterMount],
        *,
        local_mode: bool,
        eager_segments: Collection[str] = (),
    ) -> None:
        self.router = APIRouter()
        self._lock = threading.Lock()
        self._groups: dict[str, _Group] = {}
        self._listeners: list[AttachListener] = []
        self._attached_positions: list[int] = []
        position = 0
        for mount in mounts:
            if mount.local_only and not local_mode:
                continue
            self._groups.setdefault(mount.segment, _Group()).mounts.append((position, mount))
            position += 1
        unknown = set(eager_segments) - self._groups.keys()
        if unknown:
            raise ValueError(f"Eager route segments without a mount: {sorted(unknown)}")
        for segment in eager_segments:
            self.ensure_loaded(segment)

    def on_attached(self, listener: AttachListener) -> None:
        """Call ``listener`` with a group's routers each time the group is attached."""
        self._listeners.append(listener)

    def pending_segments(self) -> tuple[str, ...]:
        """Segments whose routers have not been imported yet, in declaration order."""
        return tuple(segment for segment, group in self._groups.items() if group.routers is None)

    def ensure_loaded(self, segment: str) -> None:
        """Import (if needed) and attach the routers of ``segment``; a no-op for loaded and unknown segments."""
        group = self._groups.get(segment)
        if group is None or group.loaded:
            return
        with self._lock:
            self._import(segment, group)
            self._attach_group(group)

    def load_all(self) -> None:
        """Import and attach every group (schema generation and tools that need the complete route table)."""
        for segment in self._groups:
            self.ensure_loaded(segment)

    async def preload(self) -> None:
        """Import the groups no request has asked for yet, idling between groups so requests interleave with the imports.

        The imported groups are attached together at the end, in one synchronous step no request can interleave with.
        """
        for segment in self.pending_segments():
            started = time.perf_counter()
            # ``_import`` logs the failure with the group name; the remaining groups still load.
            with contextlib.suppress(Exception), self._lock:
                self._import(segment, self._groups[segment])
            await asyncio.sleep((time.perf_counter() - started) * PRELOAD_IDLE_RATIO)
        with self._lock:
            for group in self._groups.values():
                self._attach_group(group)

    def _import(self, segment: str, group: _Group) -> None:
        """Import every router of ``group``; a failure leaves it unimported for the next attempt."""
        if group.routers is not None:
            return
        try:
            group.routers = [mount.resolve() for _, mount in group.mounts]
        except Exception:
            logger.exception("[Routes] Importing route group %r failed", segment)
            raise

    def _attach_group(self, group: _Group) -> None:
        """Attach an imported group (no-op for attached or unimported ones) and tell the listeners."""
        if group.loaded or group.routers is None:
            return
        attached = [
            self._attach(position, mount, router) for (position, mount), router in zip(group.mounts, group.routers, strict=True)
        ]
        for listener in self._listeners:
            listener(attached)
        group.loaded = True

    def _attach(self, position: int, mount: RouterMount, router: APIRouter) -> AttachedRouter:
        """Include ``router`` at its declaration position (a no-op re-include after a failed attempt is skipped)."""
        index = bisect.bisect_left(self._attached_positions, position)
        already_attached = index < len(self._attached_positions) and self._attached_positions[index] == position
        if not already_attached:
            tags: list[str | Enum] | None = [*mount.tags] or None
            self.router.include_router(router, prefix=mount.prefix, tags=tags)
            # ``include_router`` appends; moving the new include to its slot keeps the eager route order.
            self.router.routes.insert(index, self.router.routes.pop())
            self._attached_positions.insert(index, position)
        return AttachedRouter(router, mount.prefix)


def segment_of_path(scope: Scope, api_prefix: str) -> str | None:
    """The first path segment below ``api_prefix`` of the request ``scope``, or ``None`` outside the API."""
    path: str = scope["path"]
    root_path: str = scope.get("root_path", "")
    if root_path and path.startswith(root_path):
        path = path[len(root_path) :]
    prefix = f"{api_prefix.rstrip('/')}/"
    if not path.startswith(prefix):
        return None
    return path[len(prefix) :].split("/", 1)[0]


class LazyRouteMiddleware:
    """Outermost middleware: mounts the route group a request targets before routing (and the trailing-slash alias)."""

    def __init__(self, app: ASGIApp, *, loader: LazyRouteLoader, api_prefix: str) -> None:
        self.app = app
        self._loader = loader
        self._api_prefix = api_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            segment = segment_of_path(scope, self._api_prefix)
            if segment:
                self._loader.ensure_loaded(segment)
        await self.app(scope, receive, send)
