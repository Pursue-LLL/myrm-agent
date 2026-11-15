"""[INPUT]
- fastapi.routing::iter_route_contexts (POS: walks the registered routes; each included router builds its route state on first walk)

[OUTPUT]
- warm_route_table

[POS]
Builds the route state (dependency analysis, response fields) of every router the first screen did not reach, in the
idle time after the boot warm-up. FastAPI builds an included router's state the first time a request has to walk past it
(the first-screen routers are registered first, see app/api/router.py), so without this the first request to a router
below that block would build every router in front of it in one event-loop turn. The walk yields to the loop every few
routes, so a request waits behind at most the router being built.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts

from .state import logger

# A router builds its whole state at once, so the slice size only bounds the yield overhead, not the wait of a request.
ROUTES_PER_SLICE = 16


async def warm_route_table(app: FastAPI) -> None:
    """Walk every route so each included router has built its state."""
    started = time.perf_counter()
    walked = 0
    for _ in iter_route_contexts(app.routes):
        walked += 1
        if walked % ROUTES_PER_SLICE == 0:
            await asyncio.sleep(0)
    logger.info("[Startup] Route table warmed: %d routes in %.0f ms", walked, (time.perf_counter() - started) * 1000)
