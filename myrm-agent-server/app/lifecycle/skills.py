"""Application lifecycle management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.skill_optimization.ab_test_manager import ABTestManager

logger = logging.getLogger(__name__)

_ab_test_manager: "ABTestManager | None" = None


async def start_skill_optimization_listeners() -> None:
    """Initialize A/B testing and shadow testing listeners.

    Subscribes the ABTestManager to the global ToolBroadcastBus to handle
    tool completion events and trigger background shadow tests.
    """
    global _ab_test_manager
    try:
        from myrm_agent_harness.agent.streaming.broadcast.event_bus import ToolBroadcastBus
        from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter

        from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
        from app.platform_utils import get_session_factory
        from app.services.skill_optimization.ab_test_manager import ABTestManager
        from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider
        from app.services.skill_optimization.semantic_comparator import SemanticComparator
        from app.services.skill_optimization.shadow_tester import ShadowTester

        session_factory = get_session_factory()
        storage = SQLAlchemyStorage(session_factory=session_factory)

        execution_provider = ServerSkillExecutionProvider()
        event_emitter = EventEmitter()

        shadow_tester = ShadowTester(
            execution_provider=execution_provider,
            event_emitter=event_emitter,
            comparator=SemanticComparator(),
        )

        _ab_test_manager = ABTestManager(storage=storage, shadow_tester=shadow_tester)
        await _ab_test_manager.start()

        bus = await ToolBroadcastBus.get_instance()
        bus.subscribe(_ab_test_manager.handle_tool_completion)

        logger.info("Skill optimization listeners successfully started")
    except Exception as e:
        logger.error(f"Failed to start skill optimization listeners: {e}", exc_info=True)


async def shutdown_skill_optimization_listeners() -> None:
    """Gracefully shutdown ABTestManager worker pool."""
    global _ab_test_manager
    if _ab_test_manager is not None:
        await _ab_test_manager.shutdown()
        _ab_test_manager = None
