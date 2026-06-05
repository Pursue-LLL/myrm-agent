"""Optimization Scheduler Factory

Create and initialize OptimizationScheduler with all dependencies.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.optimization.scheduler import OptimizationScheduler

logger = logging.getLogger(__name__)


async def create_optimization_scheduler() -> OptimizationScheduler | None:
    """创建OptimizationScheduler实例

    集成所有依赖：
    - SkillStore (for skill metadata)
    - ServerSkillExecutionProvider (for execution data)
    - QualityCalculator (for quality scoring)
    - SkillOptimizer (for LLM-driven optimization)
    - OptimizationConfig (configuration)

    Returns:
        OptimizationScheduler实例，如果初始化失败则返回None
    """
    try:
        from myrm_agent_harness.agent.skills.evolution import SkillStore
        from myrm_agent_harness.agent.skills.optimization import (
            OptimizationConfig,
            OptimizationScheduler,
            SkillOptimizer,
            SkillSecurityValidator,
        )
        from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
        from myrm_agent_harness.agent.skills.optimization.quality_calculator import SkillQualityCalculator
        from myrm_agent_harness.toolkits.llms import llm_manager

        from app.services.skill_optimization.bootstrap import init_skill_optimization_services
        from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider
        from app.services.skill_optimization.metrics_provider import EvolutionMetricsProvider

        skill_store = SkillStore()

        execution_provider = ServerSkillExecutionProvider(skill_store=skill_store)

        metrics_provider = EvolutionMetricsProvider(skill_store)

        quality_calculator = SkillQualityCalculator(
            token_baseline=1000,
            time_baseline=10.0,
            metrics_provider=metrics_provider,
        )

        config = OptimizationConfig()

        from app.services.agent.platform_config import load_platform_model_config

        try:
            platform_model = await load_platform_model_config()
        except Exception as exc:
            logger.warning(
                "Skill optimization disabled: WebUI default model not configured (%s)",
                exc,
            )
            return None

        try:
            llm = await llm_manager.get_llm_from_config(platform_model)
        except Exception as e:
            logger.warning(f"Failed to create LLM for skill optimization: {e}")
            return None

        from app.core.utils.lock import MemoryAsyncLockProvider

        security_validator = SkillSecurityValidator(config.security)

        optimizer = SkillOptimizer(
            llm=llm,
            config=config,
            security_validator=security_validator,
            lock_provider=MemoryAsyncLockProvider(),
        )

        event_emitter = EventEmitter()

        from app.config.settings import settings

        storage_type = settings.skill_optimization_storage_type.lower()

        if storage_type == "sqlite":
            from app.adapters.skill_optimization import SQLAlchemyStorage
            from app.platform_utils import get_session_factory

            logger.info("Using SQLAlchemyStorage for skill optimization (persistent)")

            # 传入session_factory，每次操作创建独立session，避免长生命周期session问题
            storage = SQLAlchemyStorage(session_factory=get_session_factory())

            try:
                health_result = await storage.health_check()
                if not health_result.get("healthy", False):
                    logger.error("SQLAlchemyStorage health check failed, falling back to InMemoryStorage")
                    from myrm_agent_harness.agent.skills.optimization.in_memory_storage import InMemoryStorage

                    storage = InMemoryStorage()
                else:
                    logger.info("SQLAlchemyStorage health check passed")
            except Exception as e:
                logger.error(f"SQLAlchemyStorage health check error: {e}, falling back to InMemoryStorage")
                from myrm_agent_harness.agent.skills.optimization.in_memory_storage import InMemoryStorage

                storage = InMemoryStorage()
        else:
            # Use in-memory storage (default for development)
            from myrm_agent_harness.agent.skills.optimization.in_memory_storage import InMemoryStorage

            logger.info("Using InMemoryStorage for skill optimization (development)")
            storage = InMemoryStorage()

        scheduler = OptimizationScheduler(
            optimizer=optimizer,
            execution_provider=execution_provider,
            quality_calculator=quality_calculator,
            config=config,
            event_emitter=event_emitter,
            metrics_provider=metrics_provider,
        )

        init_skill_optimization_services(
            scheduler=scheduler,
            storage=storage,
            event_emitter=event_emitter,
        )

        logger.info("OptimizationScheduler and related services initialized successfully")
        return scheduler

    except Exception as e:
        logger.error(f"Failed to initialize OptimizationScheduler: {e}", exc_info=True)
        return None


__all__ = ["create_optimization_scheduler"]
