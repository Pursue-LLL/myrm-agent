"""Skill Optimization API Router"""

from fastapi import APIRouter

# Re-export init function for main/lifecycle usage
from app.api.skill_optimization.routes import (
    ab_testing,
    dashboard,
    optimization,
    system,
    versions,
)

router = APIRouter(prefix="/skill-optimization", tags=["skill-optimization"])

router.include_router(dashboard.router)
router.include_router(optimization.router)
router.include_router(ab_testing.router)
router.include_router(versions.router)
router.include_router(system.router)
