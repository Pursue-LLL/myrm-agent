"""Lazily mounted route groups: import timing, attach order, request-driven loading and preloading.

[INPUT]
- app.server.lazy_routes (POS: RouterMount / LazyRouteLoader / LazyRouteMiddleware)
- app.middleware.trailing_slash_alias::iter_route_paths (POS: 去斜杠别名中间件与路由树采集；把路由树展开为完整路径)

[OUTPUT]
- Coverage that nothing is imported before a group is needed, that a loaded aggregate equals an eagerly built one
  (route order and OpenAPI), that requests and WebSockets load their group first, and that failures are retried

[POS]
Server tests. The loader replaces a sequence of ``include_router`` calls whose imports dominate server startup; the
aggregate it builds must behave exactly like that sequence once the groups are loaded.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import textwrap
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import ModuleType

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

import app.server.lazy_routes as lazy_routes
from app.middleware.trailing_slash_alias import iter_route_paths
from app.server.lazy_routes import (
    AttachedRouter,
    LazyRouteLoader,
    LazyRouteMiddleware,
    RouterMount,
    segment_of_path,
)

API_PREFIX = "/api/v1"
_MODULE_TEMPLATE = """\
import lazy_probe_log
from fastapi import APIRouter, WebSocket

lazy_probe_log.imported.append(__name__)
router = APIRouter()
{routes}
"""


class _ProbeLog(ModuleType):
    """The module every probe router imports to record that it was imported."""

    imported: list[str]


class _Probes:
    """Writes throw-away router modules that record when they are imported."""

    def __init__(self, root: Path, log: _ProbeLog) -> None:
        self._root = root
        self._log = log

    @property
    def imported(self) -> list[str]:
        return self._log.imported

    def module(self, name: str, *paths: str, websocket: str | None = None) -> str:
        """Write ``lazy_probe_<name>``: a router with one GET per path (and one echo WebSocket), return its module name."""
        routes = [
            textwrap.dedent(
                f"""\
                @router.get({path!r})
                async def get_{index}() -> dict[str, str]:
                    return {{"module": __name__}}
                """
            )
            for index, path in enumerate(paths)
        ]
        if websocket is not None:
            routes.append(
                textwrap.dedent(
                    f"""\
                    @router.websocket({websocket!r})
                    async def echo(socket: WebSocket) -> None:
                        await socket.accept()
                        await socket.send_text("echo:" + __name__)
                        await socket.close()
                    """
                )
            )
        module_name = f"lazy_probe_{name}"
        (self._root / f"{module_name}.py").write_text(_MODULE_TEMPLATE.format(routes="\n".join(routes)))
        importlib.invalidate_caches()
        return module_name


@pytest.fixture
def probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Probes]:
    log = _ProbeLog("lazy_probe_log")
    log.imported = []
    monkeypatch.setitem(sys.modules, "lazy_probe_log", log)
    monkeypatch.syspath_prepend(str(tmp_path))
    yield _Probes(tmp_path, log)
    for name in [name for name in sys.modules if name.startswith("lazy_probe_")]:
        del sys.modules[name]


def _app_for(loader: LazyRouteLoader, *, with_middleware: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(loader.router, prefix=API_PREFIX)
    if with_middleware:
        app.add_middleware(LazyRouteMiddleware, loader=loader, api_prefix=API_PREFIX)
    return app


def _eager_reference(mounts: Sequence[RouterMount]) -> FastAPI:
    """The app an eager ``include_router`` sequence over the same mounts builds."""
    aggregate = APIRouter()
    for mount in mounts:
        aggregate.include_router(mount.resolve(), prefix=mount.prefix, tags=[*mount.tags] or None)
    app = FastAPI()
    app.include_router(aggregate, prefix=API_PREFIX)
    return app


def _mounts(probes: _Probes) -> list[RouterMount]:
    return [
        RouterMount("alpha", probes.module("a1", "/alpha/one")),
        RouterMount("beta", probes.module("b1", "/one"), prefix="/beta", tags=("beta-tag",)),
        RouterMount("alpha", probes.module("a2", "/alpha/two", "/alpha/two/{item}"), tags=("alpha-tag", "shared")),
        RouterMount("gamma", probes.module("c1", "/gamma/one")),
    ]


def test_nothing_is_imported_until_a_group_loads(probes: _Probes) -> None:
    loader = LazyRouteLoader(_mounts(probes), local_mode=True)

    assert probes.imported == []
    assert loader.pending_segments() == ("alpha", "beta", "gamma")

    loader.ensure_loaded("alpha")

    assert sorted(probes.imported) == ["lazy_probe_a1", "lazy_probe_a2"]
    assert loader.pending_segments() == ("beta", "gamma")

    loader.ensure_loaded("alpha")
    loader.ensure_loaded("no-such-segment")

    assert sorted(probes.imported) == ["lazy_probe_a1", "lazy_probe_a2"]


@pytest.mark.parametrize("load_order", [("alpha", "beta", "gamma"), ("gamma", "beta", "alpha"), ("beta", "gamma", "alpha")])
def test_a_loaded_aggregate_equals_an_eagerly_built_one_whatever_the_load_order(
    probes: _Probes, load_order: tuple[str, ...]
) -> None:
    mounts = _mounts(probes)
    loader = LazyRouteLoader(mounts, local_mode=True)
    app = _app_for(loader)
    for segment in load_order:
        loader.ensure_loaded(segment)
    reference = _eager_reference(mounts)

    assert list(iter_route_paths(app.routes)) == list(iter_route_paths(reference.routes))
    assert app.openapi() == reference.openapi()
    assert list(app.openapi()["paths"]) == list(reference.openapi()["paths"])


def test_local_only_mounts_follow_the_deploy_mode(probes: _Probes) -> None:
    mounts = [
        RouterMount("alpha", probes.module("a1", "/alpha/one")),
        RouterMount("events", probes.module("e1", "/events/stream"), local_only=True),
    ]

    assert LazyRouteLoader(mounts, local_mode=True).pending_segments() == ("alpha", "events")
    assert LazyRouteLoader(mounts, local_mode=False).pending_segments() == ("alpha",)


def test_eager_segments_load_at_construction_and_unknown_ones_are_rejected(probes: _Probes) -> None:
    mounts = _mounts(probes)

    loader = LazyRouteLoader(mounts, local_mode=True, eager_segments=("beta",))

    assert probes.imported == ["lazy_probe_b1"]
    assert loader.pending_segments() == ("alpha", "gamma")
    with pytest.raises(ValueError, match="nope"):
        LazyRouteLoader(mounts, local_mode=True, eager_segments=("nope",))


def test_a_factory_mount_calls_the_attribute_and_other_attributes_are_not_routers(probes: _Probes) -> None:
    module_name = probes.module("f1", "/factory/one")
    module = importlib.import_module(module_name)
    vars(module).update(build=lambda: module.router, not_a_router=3)

    assert RouterMount("factory", module_name, attr="build", factory=True).resolve() is module.router
    with pytest.raises(TypeError, match="not an APIRouter"):
        RouterMount("factory", module_name, attr="not_a_router").resolve()


def test_a_failed_import_leaves_the_group_pending_and_the_next_request_retries(
    probes: _Probes, caplog: pytest.LogCaptureFixture
) -> None:
    mounts = [
        RouterMount("alpha", probes.module("a1", "/alpha/one")),
        RouterMount("late", "lazy_probe_late"),
    ]
    loader = LazyRouteLoader(mounts, local_mode=True)

    with caplog.at_level("ERROR", logger=lazy_routes.logger.name), pytest.raises(ModuleNotFoundError):
        loader.ensure_loaded("late")

    assert "Importing route group 'late' failed" in caplog.text
    assert loader.pending_segments() == ("alpha", "late")

    probes.module("late", "/late/one")
    loader.ensure_loaded("late")
    loader.ensure_loaded("alpha")

    assert loader.pending_segments() == ()
    served = [path for path in iter_route_paths(_app_for(loader).routes) if path.startswith(API_PREFIX)]
    assert served == [f"{API_PREFIX}/alpha/one", f"{API_PREFIX}/late/one"]


def test_attach_listeners_receive_the_routers_of_the_group_with_their_prefixes(probes: _Probes) -> None:
    loader = LazyRouteLoader(_mounts(probes), local_mode=True)
    attached: list[Sequence[AttachedRouter]] = []
    loader.on_attached(attached.append)

    loader.ensure_loaded("beta")
    loader.ensure_loaded("alpha")
    loader.ensure_loaded("alpha")

    assert [[mounted.prefix for mounted in group] for group in attached] == [["/beta"], ["", ""]]


@pytest.mark.parametrize(
    ("path", "root_path", "expected"),
    [
        ("/api/v1/chats", "", "chats"),
        ("/api/v1/chats/", "", "chats"),
        ("/api/v1/chats/abc/messages", "", "chats"),
        ("/api/v1/", "", ""),
        ("/api/v1", "", None),
        ("/api/v10/chats", "", None),
        ("/health", "", None),
        ("/proxy/api/v1/files/x", "/proxy", "files"),
        ("/api/v1/files/x", "/proxy", "files"),
        ("/proxyapi/v1/files/x", "/proxy", None),
    ],
)
def test_segment_of_path_names_the_group_below_the_api_prefix(path: str, root_path: str, expected: str | None) -> None:
    assert segment_of_path({"path": path, "root_path": root_path}, API_PREFIX) == expected


def test_a_request_loads_its_group_before_routing_and_other_paths_load_nothing(probes: _Probes) -> None:
    loader = LazyRouteLoader(_mounts(probes), local_mode=True)
    client = TestClient(_app_for(loader, with_middleware=True))

    assert client.get(f"{API_PREFIX}/unknown/x").status_code == 404
    assert client.get("/other").status_code == 404
    assert probes.imported == []

    response = client.get(f"{API_PREFIX}/alpha/one")

    assert response.status_code == 200
    assert response.json() == {"module": "lazy_probe_a1"}
    assert loader.pending_segments() == ("beta", "gamma")

    assert client.get(f"{API_PREFIX}/beta/one").json() == {"module": "lazy_probe_b1"}
    assert client.get(f"{API_PREFIX}/alpha/two/7").json() == {"module": "lazy_probe_a2"}


def test_a_websocket_loads_its_group_before_routing(probes: _Probes) -> None:
    mounts = [RouterMount("ws", probes.module("w1", websocket="/echo"), prefix="/ws")]
    loader = LazyRouteLoader(mounts, local_mode=True)
    client = TestClient(_app_for(loader, with_middleware=True))

    with client.websocket_connect(f"{API_PREFIX}/ws/echo") as socket:
        assert socket.receive_text() == "echo:lazy_probe_w1"

    assert loader.pending_segments() == ()


def test_groups_attached_after_requests_were_served_are_routed(probes: _Probes) -> None:
    """The aggregate keeps serving what it served and gains what loads later; FastAPI must pick the new includes up."""
    loader = LazyRouteLoader(_mounts(probes), local_mode=True, eager_segments=("gamma",))
    client = TestClient(_app_for(loader))
    assert client.get(f"{API_PREFIX}/gamma/one").status_code == 200
    assert client.get(f"{API_PREFIX}/alpha/one").status_code == 404

    loader.ensure_loaded("alpha")
    assert client.get(f"{API_PREFIX}/alpha/one").status_code == 200
    assert client.get(f"{API_PREFIX}/gamma/one").status_code == 200

    loader.ensure_loaded("beta")
    assert client.get(f"{API_PREFIX}/beta/one").status_code == 200


def test_the_openapi_hook_loads_every_group_first(probes: _Probes) -> None:
    from app.server.openapi_security import install_custom_openapi

    mounts = _mounts(probes)
    loader = LazyRouteLoader(mounts, local_mode=True)
    app = _app_for(loader)
    install_custom_openapi(app, prepare=loader.load_all)

    paths = set(app.openapi()["paths"])

    assert loader.pending_segments() == ()
    assert paths == {
        f"{API_PREFIX}{path}" for path in ("/alpha/one", "/beta/one", "/alpha/two", "/alpha/two/{item}", "/gamma/one")
    }


async def test_preload_loads_the_pending_groups_idling_between_them(probes: _Probes, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lazy_routes, "PRELOAD_IDLE_RATIO", 0.0)
    loader = LazyRouteLoader(_mounts(probes), local_mode=True)
    loader.ensure_loaded("beta")
    ticks = 0
    stop = asyncio.Event()

    async def ticker() -> None:
        nonlocal ticks
        while not stop.is_set():
            ticks += 1
            await asyncio.sleep(0)

    ticking = asyncio.create_task(ticker())
    await loader.preload()
    stop.set()
    await ticking

    assert loader.pending_segments() == ()
    assert ticks >= 2


async def test_preload_continues_past_a_group_that_fails_to_import(probes: _Probes, caplog: pytest.LogCaptureFixture) -> None:
    mounts = [
        RouterMount("broken", "lazy_probe_missing"),
        RouterMount("alpha", probes.module("a1", "/alpha/one")),
    ]
    loader = LazyRouteLoader(mounts, local_mode=True)

    with caplog.at_level("ERROR", logger=lazy_routes.logger.name):
        await loader.preload()

    assert loader.pending_segments() == ("broken",)
    assert "Importing route group 'broken' failed" in caplog.text
