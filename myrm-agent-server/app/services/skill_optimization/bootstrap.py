"""Skill optimization service bootstrap and shared instances."""

from __future__ import annotations

from typing import cast

from myrm_agent_harness.agent.skills.optimization import EventEmitter, InMemoryAggregator
from myrm_agent_harness.agent.skills.optimization.scheduler import OptimizationScheduler

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage

_scheduler_instance: OptimizationScheduler | None = None
_storage_instance: SQLAlchemyStorage | None = None
_event_emitter_instance: EventEmitter | None = None
_aggregator_instance: InMemoryAggregator | None = None


def init_skill_optimization_services(
    scheduler: object,
    storage: object,
    event_emitter: object,
    aggregator: object | None = None,
) -> None:
    """Register skill optimization singletons after scheduler startup."""
    global _scheduler_instance, _storage_instance, _event_emitter_instance, _aggregator_instance
    _scheduler_instance = cast(OptimizationScheduler, scheduler)
    _storage_instance = cast(SQLAlchemyStorage, storage)
    _event_emitter_instance = cast(EventEmitter, event_emitter)
    _aggregator_instance = cast(InMemoryAggregator | None, aggregator)


def get_registered_scheduler() -> OptimizationScheduler | None:
    return _scheduler_instance


def get_registered_storage() -> SQLAlchemyStorage | None:
    return _storage_instance


def get_registered_event_emitter() -> EventEmitter | None:
    return _event_emitter_instance


def get_registered_aggregator() -> InMemoryAggregator | None:
    return _aggregator_instance
