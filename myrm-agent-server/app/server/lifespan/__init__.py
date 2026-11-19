"""Server lifespan.

[INPUT]
- .app (POS: the FastAPI lifespan)
- .startup (POS: startup phases of the server lifespan)
- .state (POS: process-wide startup state shared by the lifespan phases)

[OUTPUT]
- optimized_lifespan plus the startup phases and the logger the tests inspect.

[POS]
Aggregate exit of the lifespan package.
"""

from __future__ import annotations

from .app import optimized_lifespan
from .startup import _phase_1a_sequential, _phase_1b_parallel
from .state import logger

__all__ = [
    "optimized_lifespan",
    "logger",
    "_phase_1a_sequential",
    "_phase_1b_parallel",
]
