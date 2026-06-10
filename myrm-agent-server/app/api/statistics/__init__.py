"""Statistics API package entrypoint.

[INPUT]
- fastapi::APIRouter (POS: FastAPI router composition)
- app.api.statistics.router (POS: base statistics API routes)
- app.api.statistics.agent_usage (POS: per-agent usage analytics routes)
- app.api.statistics.growth_dashboard (POS: growth dashboard routes)
- app.api.statistics.daily_journal (POS: daily journal aggregation routes)

[OUTPUT]
- build_statistics_router: compose statistics routers on explicit application startup.

[POS]
Statistics package entrypoint. Keeps submodule imports lightweight and composes routers only when
the main API router asks for them.
"""

from fastapi import APIRouter


def build_statistics_router() -> APIRouter:
    """Build the statistics API router without import-time submodule side effects."""
    from app.api.statistics.agent_usage import router as agent_usage_router
    from app.api.statistics.daily_journal import router as daily_journal_router
    from app.api.statistics.growth_dashboard import router as growth_dashboard_router
    from app.api.statistics.router import router as base_router

    statistics_router = APIRouter()
    statistics_router.include_router(base_router)
    statistics_router.include_router(agent_usage_router)
    statistics_router.include_router(growth_dashboard_router)
    statistics_router.include_router(daily_journal_router)
    return statistics_router


__all__ = ["build_statistics_router"]
