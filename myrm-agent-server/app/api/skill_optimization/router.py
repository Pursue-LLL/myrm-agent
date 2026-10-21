"""Skill Optimization API Router"""

from fastapi import APIRouter

from app.api.skill_optimization.routes import versions

router = APIRouter(prefix="/skill-optimization", tags=["skill-optimization"])

router.include_router(versions.router)
