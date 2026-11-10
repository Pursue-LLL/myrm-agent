"""Cyclic-GC policy for the boot of a server process.

[INPUT]
- gc (POS: the stdlib cycle collector)

[OUTPUT]
- defer_collection: pause the cycle collector while the process boots
- settle_collection: freeze the boot heap and resume collection
- settle_collection_after: settle once the post-ready boot work ends, or after a deadline

[POS]
Importing the server loads thousands of modules and allocates millions of long-lived objects, and every full
collection walks all of them again: five or six pauses of 60-400 ms add about a second before the HTTP server
answers. Nothing the boot allocates is garbage, so the collector stays off until startup has settled. The surviving
heap is then frozen, so later full collections skip it, and collection resumes.
Only the process entry points pause the collector (`run.py` through the uvicorn runner, the desktop sidecar through
its runtime hook); tests and tools that import `app` keep the default behaviour, and `settle_collection` does nothing
for them.
"""

from __future__ import annotations

import asyncio
import gc
from typing import TypeVar

_T = TypeVar("_T")

# A boot that never settles (a hung warmup) must not leave the process without cycle collection.
SETTLE_DEADLINE_SECONDS = 30.0


def defer_collection() -> None:
    """Pause the cycle collector; reference counting keeps freeing everything that is not in a cycle."""
    gc.disable()


def settle_collection() -> None:
    """End the boot pause: move the boot heap out of future collections, then resume. No-op while collection runs."""
    if gc.isenabled():
        return
    gc.freeze()
    gc.enable()


def settle_collection_after(boot_work: asyncio.Future[_T], *, deadline_seconds: float = SETTLE_DEADLINE_SECONDS) -> None:
    """Settle when ``boot_work`` ends (however it ends), or after ``deadline_seconds`` if it never does."""
    deadline = asyncio.get_running_loop().call_later(deadline_seconds, settle_collection)

    def _settle(_: asyncio.Future[_T]) -> None:
        deadline.cancel()
        settle_collection()

    boot_work.add_done_callback(_settle)
