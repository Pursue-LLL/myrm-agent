"""Cron job REST endpoints.

All endpoints delegate to ``CronManager`` — no direct DB access.
"""

from fastapi import APIRouter

from .blueprints import router as blueprints_router
from .heartbeat import router as heartbeat_router
from .jobs import router as jobs_router
from .push_messages import router as push_messages_router
from .runs import router as runs_router
from .scheduler_health import router as scheduler_health_router
from .stats import router as stats_router
from .triggers import router as triggers_router

router = APIRouter()

# Fixed-path routers MUST be registered before jobs_router,
# because jobs_router has /{job_id} wildcard that would otherwise
# swallow paths like /push-messages, /runs/all, /stats/usage, etc.
router.include_router(blueprints_router)
router.include_router(heartbeat_router)
router.include_router(scheduler_health_router)
router.include_router(triggers_router)
router.include_router(stats_router)
router.include_router(push_messages_router)
router.include_router(runs_router)
router.include_router(jobs_router)
