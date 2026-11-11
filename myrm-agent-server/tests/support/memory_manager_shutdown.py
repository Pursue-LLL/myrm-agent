"""Close the cached memory managers without waiting on a connection that can no longer answer.

[INPUT]
- app.core.memory.adapters.setup::shutdown_cached_memory_managers (POS: Closes every cached MemoryManager and the embedded vector stores)

[OUTPUT]
- shutdown_cached_memory_managers_bounded: runs that shutdown, and after ``timeout`` seconds gives up on whatever is still open

[POS]
Server pytest-only teardown helper, used by the per-test reset in tests/api/agent/conftest.py. That reset runs in a fresh event loop,
after the loop that opened each manager's connections has closed. aiosqlite hands every result back through the loop that asked
for it, so a worker thread that finished a query after its loop was gone has died, and its connection never answers again:
awaiting that close holds the whole session until the CI time limit.
"""

from __future__ import annotations

import asyncio
import logging

_logger = logging.getLogger(__name__)

# A healthy close takes milliseconds; the bound only has to outlast a slow CI runner.
CLOSE_TIMEOUT_SECONDS = 5.0
# Closing a connection waits on its worker once more while the close is being cancelled, so each cancel moves the close only one
# await further; a few rounds unwind it.
_CANCEL_ROUNDS = 5
_CANCEL_ROUND_SECONDS = 0.2


async def shutdown_cached_memory_managers_bounded(timeout: float = CLOSE_TIMEOUT_SECONDS) -> None:
    from app.core.memory.adapters.setup import shutdown_cached_memory_managers

    shutdown = asyncio.create_task(shutdown_cached_memory_managers())
    await asyncio.wait({shutdown}, timeout=timeout)
    if shutdown.done():
        shutdown.result()
        return

    _logger.warning("Cached memory managers did not close within %.1fs; abandoning the ones still open", timeout)
    for _ in range(_CANCEL_ROUNDS):
        shutdown.cancel()
        await asyncio.wait({shutdown}, timeout=_CANCEL_ROUND_SECONDS)
        if shutdown.done():
            return
