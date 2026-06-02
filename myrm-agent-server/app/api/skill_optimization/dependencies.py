from __future__ import annotations

import typing
from collections.abc import Callable
from typing import cast

from fastapi import HTTPException
from myrm_agent_harness.agent.skills.optimization import EventEmitter, InMemoryAggregator
from myrm_agent_harness.agent.skills.optimization.protocols import SkillExecutionProvider
from myrm_agent_harness.agent.skills.optimization.scheduler import OptimizationScheduler
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.services.skill_optimization.ab_test_manager import ABTestManager

_insights_instance = None

_recommender_instance = None

_ab_test_manager_instance: ABTestManager | None = None


@typing.no_type_check
def _new_server_skill_execution_provider() -> SkillExecutionProvider:
    from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider

    return ServerSkillExecutionProvider()


def get_scheduler() -> OptimizationScheduler:
    """Return OptimizationScheduler instance."""
    from app.core.infra.server_globals import get_optimization_scheduler

    scheduler = get_optimization_scheduler()
    if scheduler is None:
        raise HTTPException(
            status_code=503, detail="OptimizationScheduler not initialized. Please start the skill optimization service."
        )
    return cast(OptimizationScheduler, scheduler)


def get_storage() -> SQLAlchemyStorage:
    """Return SkillOptimizationStorage instance."""
    from app.services.skill_optimization.bootstrap import get_registered_storage

    storage = get_registered_storage()
    if storage is not None:
        return storage

    from app.platform_utils import get_session_factory

    factory = get_session_factory()
    return SQLAlchemyStorage(
        session_factory=cast(Callable[..., AsyncSession], factory),
    )


def get_event_emitter() -> EventEmitter:
    """Return EventEmitter instance."""
    from app.services.skill_optimization.bootstrap import get_registered_event_emitter

    emitter = get_registered_event_emitter()
    if emitter is not None:
        return emitter
    return EventEmitter()


def get_aggregator() -> InMemoryAggregator:
    """Return SkillQualityAggregator instance."""
    from app.services.skill_optimization.bootstrap import get_registered_aggregator

    aggregator = get_registered_aggregator()
    if aggregator is not None:
        return aggregator
    storage = get_storage()
    return InMemoryAggregator(storage)


def get_ab_test_manager() -> ABTestManager:
    """Return ABTestManager instance (lazy init)."""
    global _ab_test_manager_instance
    if _ab_test_manager_instance is None:
        from app.services.skill_optimization.semantic_comparator import SemanticComparator
        from app.services.skill_optimization.shadow_tester import ShadowTester

        storage = get_storage()
        event_emitter = get_event_emitter()
        exec_provider = _new_server_skill_execution_provider()
        shadow_tester = ShadowTester(exec_provider, event_emitter, comparator=SemanticComparator())
        _ab_test_manager_instance = ABTestManager(storage, shadow_tester)
    return _ab_test_manager_instance


def init_skill_optimization_services(
    scheduler: object,
    storage: object,
    event_emitter: object,
    aggregator: object | None = None,
) -> None:
    """Initialize skill optimization service instances."""
    from app.services.skill_optimization.bootstrap import init_skill_optimization_services as _init

    _init(
        scheduler=scheduler,
        storage=storage,
        event_emitter=event_emitter,
        aggregator=aggregator,
    )
