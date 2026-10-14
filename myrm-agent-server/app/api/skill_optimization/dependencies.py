from __future__ import annotations

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage


def get_storage() -> SQLAlchemyStorage:
    """Return SkillOptimizationStorage instance."""
    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage

    return get_skill_optimization_storage()
