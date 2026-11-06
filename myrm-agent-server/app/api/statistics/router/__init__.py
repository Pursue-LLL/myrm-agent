"""Statistics API router.

[INPUT]
- .common (POS: shared router)

[OUTPUT]
- router (all statistics endpoints mounted), settings

[POS]
Aggregate exit of the statistics router package.
"""

from __future__ import annotations

from app.api.statistics.learning_loop import router as learning_loop_router
from app.api.statistics.learning_timeline import router as learning_timeline_router
from app.api.statistics.prompt_cache_radar import router as prompt_cache_radar_router
from app.api.statistics.session_analytics import router as session_router
from app.api.statistics.session_model_sessions import router as model_sessions_router
from app.api.statistics.session_trace import router as session_trace_router
from app.config.settings import settings

from . import activity, tools, usage  # noqa: F401  (register endpoint routes before mounting)
from .common import router

router.include_router(session_router)
router.include_router(session_trace_router)
router.include_router(prompt_cache_radar_router)
router.include_router(model_sessions_router)
router.include_router(learning_timeline_router)
router.include_router(learning_loop_router)

__all__ = ["router", "settings"]
