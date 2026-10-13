from __future__ import annotations

import typing

from myrm_agent_harness.agent.skills.optimization import EventEmitter
from myrm_agent_harness.agent.skills.optimization.protocols import SkillExecutionProvider

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.services.skill_optimization.ab_test_manager import ABTestManager

_ab_test_manager_instance: ABTestManager | None = None


@typing.no_type_check
def _new_server_skill_execution_provider() -> SkillExecutionProvider:
    from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider

    return ServerSkillExecutionProvider()


def get_storage() -> SQLAlchemyStorage:
    """Return SkillOptimizationStorage instance."""
    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage

    return get_skill_optimization_storage()


def get_event_emitter() -> EventEmitter:
    """Return a request-scoped EventEmitter."""
    return EventEmitter()


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
