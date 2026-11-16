"""Web fetch toolkit.

[INPUT]
- engine::FetchEngine, FailedResult, SuccessResult (POS: layered single-page fetch engine) [lazy]

[OUTPUT]
- FetchEngine: layered fetch engine (re-export)
- FailedResult: failed fetch result model (re-export)
- SuccessResult: successful fetch result model (re-export)
- web_fetch_tools: global FetchEngine instance, created on first access

[POS]
Web fetch toolkit entry point. Re-exports the core single-page fetch engine. The engine, its HTTP stack and the HTML
parser load on first access, so importing a submodule (the agent runtime registers the spill callbacks on every run,
fetching or not) does not pay for them.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .engine import FailedResult, FetchEngine, SuccessResult

    web_fetch_tools: FetchEngine

__all__ = [
    "FailedResult",
    "FetchEngine",
    "SuccessResult",
    "web_fetch_tools",
]

_ENGINE_EXPORTS = frozenset({"FailedResult", "FetchEngine", "SuccessResult"})
_instance_lock = threading.Lock()


def __getattr__(name: str) -> object:
    """Load the engine on first access; the global instance is created once, whichever thread asks first."""
    if name in _ENGINE_EXPORTS:
        from . import engine

        value = getattr(engine, name)
        globals()[name] = value
        return value
    if name == "web_fetch_tools":
        with _instance_lock:
            if name not in globals():
                from .engine import FetchEngine

                globals()[name] = FetchEngine()
            return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
