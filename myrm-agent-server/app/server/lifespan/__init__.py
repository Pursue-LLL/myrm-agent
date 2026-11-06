"""Server lifespan.

[INPUT]
- .app (POS: optimized_lifespan)

[OUTPUT]
- optimized_lifespan plus the phase helpers the tests inspect.

[POS]
Aggregate exit of the lifespan package.
"""

from __future__ import annotations

from .app import optimized_lifespan
from .shutdown import _shutdown
from .startup import (
    _apply_code_execution_config,
    _dispatch_startup_event,
    _phase_1a_sequential,
    _phase_1b_parallel,
    _preload_agent_tool_layers,
    _register_db_pool_metrics_task,
    _seed_trunk_templates,
)
from .state import logger

__all__ = [
    "optimized_lifespan",
    "logger",
    "_apply_code_execution_config",
    "_dispatch_startup_event",
    "_phase_1a_sequential",
    "_phase_1b_parallel",
    "_preload_agent_tool_layers",
    "_register_db_pool_metrics_task",
    "_seed_trunk_templates",
    "_shutdown",
]
