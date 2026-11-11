"""PyInstaller runtime hook: keep the cycle collector off while the bundled server imports itself.

The sidecar entry imports the whole server before uvicorn starts, and every full collection during that import walks
all the objects the import has allocated so far: five or six pauses add about a second to the time before the first
request is answered. Nothing the import allocates is garbage, so the collector stays off until the server lifespan has
finished its background start-up work; ``app.startup.gc_policy.settle_collection_after`` then freezes the surviving
heap and turns collection back on.

[INPUT]
- gc (POS: the stdlib cycle collector)

[OUTPUT]
- Import side effect: the cycle collector is off until ``app.startup.gc_policy.settle_collection_after`` freezes the
  boot heap and turns it back on

[POS]
Runtime hook that build.py injects with ``--runtime-hook``; it runs before the sidecar entry imports the server, so the
whole import goes without full collections.
"""

import gc

gc.disable()
