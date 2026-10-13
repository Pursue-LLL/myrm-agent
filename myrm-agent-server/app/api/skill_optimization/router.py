"""Skill Optimization API Router"""

from fastapi import APIRouter

from app.api.skill_optimization.routes import (
    ab_testing,
    versions,
)

router = APIRouter(prefix="/skill-optimization", tags=["skill-optimization"])

router.include_router(ab_testing.router)
router.include_router(versions.router)
