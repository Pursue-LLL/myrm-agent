from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.optimization.config import OptimizationConfig
from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
from myrm_agent_harness.agent.skills.optimization.in_memory_storage import InMemoryStorage
from myrm_agent_harness.agent.skills.optimization.optimizer import SkillOptimizer
from myrm_agent_harness.agent.skills.optimization.quality_calculator import SkillQualityCalculator
from myrm_agent_harness.agent.skills.optimization.scheduler import OptimizationScheduler
from myrm_agent_harness.agent.skills.optimization.security import SkillSecurityValidator

from app.api.skill_optimization.dependencies import init_skill_optimization_services
from app.api.skill_optimization.metrics_provider import EvolutionMetricsProvider
from app.api.skill_optimization.router import router as skill_optimization_router
from app.services.skill_optimization.execution_provider import ServerSkillExecutionProvider


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI(title="Skill Optimization Test App")

    # Initialize in-memory dependencies
    skill_store = SkillStore()
    execution_provider = ServerSkillExecutionProvider(skill_store=skill_store)
    metrics_provider = EvolutionMetricsProvider(skill_store)
    quality_calculator = SkillQualityCalculator(
        token_baseline=1000,
        time_baseline=10.0,
        metrics_provider=metrics_provider,
    )
    config = OptimizationConfig()
    security_validator = SkillSecurityValidator(config.security)

    # Mock LLM for optimizer
    mock_llm = AsyncMock()
    optimizer = SkillOptimizer(
        llm=mock_llm,
        config=config,
        security_validator=security_validator,
    )

    event_emitter = EventEmitter()

    scheduler = OptimizationScheduler(
        optimizer=optimizer,
        execution_provider=execution_provider,
        quality_calculator=quality_calculator,
        config=config,
        event_emitter=event_emitter,
        metrics_provider=metrics_provider,
    )

    storage = InMemoryStorage()

    init_skill_optimization_services(
        scheduler=scheduler,
        storage=storage,
        event_emitter=event_emitter,
    )

    # Override dependencies that require DB
    from app.database.connection import get_db

    async def mock_get_deploy_identity():
        return "test-user-id"

    async def mock_get_db():
        yield AsyncMock()

    pass
    app.dependency_overrides[get_db] = mock_get_db

    # Set the global scheduler for the router dependency
    from app.core.infra.server_globals import set_optimization_scheduler

    set_optimization_scheduler(scheduler)

    app.include_router(skill_optimization_router, prefix="/api/v1")

    return app


@pytest.fixture
def client(app: FastAPI):
    with TestClient(app) as client:
        yield client
