"""Skill optimization runtime singleton (ABTestManager lifecycle).

[INPUT]
- app.services.skill_optimization.ab_test_manager::ABTestManager

[OUTPUT]
- get_skill_optimization_runtime: return started runtime or None
- require_ab_test_manager: return manager or raise RuntimeError
- start_skill_optimization_runtime / shutdown_skill_optimization_runtime

[POS]
Single process-wide ABTestManager instance. HTTP deps and lifecycle share this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.skill_optimization.ab_test_manager import ABTestManager

logger = logging.getLogger(__name__)


@dataclass
class SkillOptimizationRuntimeState:
    manager: ABTestManager | None = None
    start_error: str | None = None


_state = SkillOptimizationRuntimeState()


def get_skill_optimization_runtime() -> SkillOptimizationRuntimeState:
    return _state


def require_ab_test_manager() -> ABTestManager:
    if _state.manager is None:
        detail = _state.start_error or "Skill optimization runtime not started"
        raise RuntimeError(detail)
    return _state.manager


async def start_skill_optimization_runtime() -> None:
    """Construct, start, and subscribe ABTestManager to ToolBroadcastBus."""
    if _state.manager is not None:
        return

    from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
    from myrm_agent_harness.agent.streaming.broadcast.event_bus import ToolBroadcastBus

    from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
    from app.platform_utils import get_session_factory
    from app.services.skill_optimization.ab_test_manager import ABTestManager
    from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider
    from app.services.skill_optimization.semantic_comparator import SemanticComparator
    from app.services.skill_optimization.shadow_tester import ShadowTester

    try:
        session_factory = get_session_factory()
        storage = SQLAlchemyStorage(session_factory=session_factory)
        execution_provider = ServerSkillExecutionProvider()
        event_emitter = EventEmitter()
        shadow_tester = ShadowTester(
            execution_provider=execution_provider,
            event_emitter=event_emitter,
            comparator=SemanticComparator(),
        )
        manager = ABTestManager(storage=storage, shadow_tester=shadow_tester)
        await manager.start()

        bus = await ToolBroadcastBus.get_instance()
        bus.subscribe(manager.handle_tool_completion)

        _state.manager = manager
        _state.start_error = None
        logger.info("Skill optimization runtime started")
    except Exception as exc:
        _state.start_error = str(exc)
        logger.error("Failed to start skill optimization runtime: %s", exc, exc_info=True)
        raise


async def shutdown_skill_optimization_runtime() -> None:
    if _state.manager is not None:
        await _state.manager.shutdown()
        _state.manager = None
    _state.start_error = None
