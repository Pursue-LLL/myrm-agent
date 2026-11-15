"""The route-table warm-up builds what the first screen did not reach, without holding the event loop.

[INPUT]
- app.server.lifespan.route_warmup (POS: walks the routes after the boot warm-up)
- fastapi.routing (POS: builds an included router's route state the first time a request walks past it)

[OUTPUT]
- Coverage of the framework behaviour the first-screen ordering depends on (a request builds only the routers in front
  of its own, the walk builds the rest, a later request builds nothing) and of the walk's slicing and logging

[POS]
Server tests. The routers below the first-screen block would otherwise build their route state inside the first request
that reaches them; if a FastAPI upgrade changes when that state is built, the first test fails and the ordering in
app/api/router.py has to be reconsidered.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest import mock

import fastapi.routing
import httpx
import pytest
from fastapi import APIRouter, FastAPI

from app.server.lifespan import route_warmup
from app.server.lifespan.state import logger


@pytest.fixture
def route_state_builds() -> Iterator[mock.MagicMock]:
    """A spy on the framework call that builds one route's per-router route state; its call count is the build count."""
    context = fastapi.routing._EffectiveRouteContext
    with mock.patch.object(context, "from_api_route", wraps=context.from_api_route) as spy:
        yield spy


def _router(name: str, routes: int) -> APIRouter:
    router = APIRouter()
    for index in range(routes):

        async def endpoint() -> str:
            return name

        router.add_api_route(f"/{index}", endpoint, methods=["GET"])
    return router


def _app(*routers: tuple[str, int]) -> FastAPI:
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
    api = APIRouter()
    for name, routes in routers:
        api.include_router(_router(name, routes), prefix=f"/{name}")
    app.include_router(api, prefix="/api")
    return app


async def _get(app: FastAPI, path: str) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).status_code == 200


async def test_a_request_builds_the_routers_in_front_of_its_own_and_the_walk_builds_the_rest(
    route_state_builds: mock.MagicMock,
) -> None:
    app = _app(("a", 3), ("b", 4), ("c", 5))
    assert route_state_builds.call_count == 0

    await _get(app, "/api/a/0")
    assert route_state_builds.call_count == 3, "a request must build only the routers it walks past, here router a alone"

    await route_warmup.warm_route_table(app)
    assert route_state_builds.call_count == 12, "the walk must build the routers no request has reached"

    await _get(app, "/api/c/0")
    await _get(app, "/api/b/1")
    assert route_state_builds.call_count == 12, "a request after the walk must find every router built"


async def test_the_walk_yields_to_the_event_loop_between_slices(caplog: pytest.LogCaptureFixture) -> None:
    routes = route_warmup.ROUTES_PER_SLICE * 4
    app = _app(("a", routes // 2), ("b", routes // 2))
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    ticking = asyncio.create_task(ticker())
    try:
        with caplog.at_level("INFO", logger=logger.name):
            await route_warmup.warm_route_table(app)
    finally:
        ticking.cancel()

    assert ticks >= routes // route_warmup.ROUTES_PER_SLICE - 1, "the walk must hand the loop back every slice"
    assert f"Route table warmed: {routes} routes" in caplog.text
