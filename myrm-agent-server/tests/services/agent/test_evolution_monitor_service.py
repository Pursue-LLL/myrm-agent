"""Startup of the skill evolution monitor service.

The service needs only the evolution model; an embedding model is not part of
its prerequisites because skill evolution holds no semantic index.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.evolution import monitor_service


@pytest.fixture(autouse=True)
def _fresh_singleton() -> Iterator[None]:
    original = monitor_service._monitor_service
    monitor_service._monitor_service = None
    yield
    monitor_service._monitor_service = original


@pytest.mark.asyncio
async def test_monitor_starts_with_evolution_model_only() -> None:
    integration = MagicMock()
    integration.start_background_queue = AsyncMock()
    integration_factory = MagicMock(return_value=integration)
    embedding_requirement = AsyncMock(side_effect=RuntimeError("embedding must not be required"))

    with (
        patch(
            "myrm_agent_harness.agent.skills.evolution.infra.integration.get_global_evolution_integration",
            return_value=None,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new=AsyncMock(return_value=MagicMock()),
        ),
        patch(
            "app.services.agent.platform_config.load_platform_evolution_model_config",
            new=AsyncMock(return_value=SimpleNamespace()),
        ),
        patch("app.services.agent.platform_config.require_platform_embedding_config", new=embedding_requirement),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=SimpleNamespace(search_cfg=None, search_is_user_configured=False)),
        ),
        patch("myrm_agent_harness.agent.skills.evolution.pipeline.screener.EvolutionScreener") as screener_cls,
        patch.object(monitor_service, "EvolutionIntegration", integration_factory),
        patch.object(monitor_service.SkillEvolutionMonitorService, "start", new=AsyncMock()) as start,
    ):
        await monitor_service.init_evolution_monitor_service()

    integration_factory.assert_called_once()
    assert "vector_store" not in integration_factory.call_args.kwargs
    assert "embedding" not in integration_factory.call_args.kwargs
    embedding_requirement.assert_not_awaited()
    assert screener_cls.call_args.kwargs["store"] is integration.store
    assert integration.screener is screener_cls.return_value
    integration.start_background_queue.assert_awaited_once()
    start.assert_awaited_once()
    assert monitor_service._monitor_service is not None


@pytest.mark.asyncio
async def test_start_is_skipped_without_evolution_engine() -> None:
    integration = SimpleNamespace(engine=None, store=MagicMock())
    service = monitor_service.SkillEvolutionMonitorService(integration)  # type: ignore[arg-type]

    await service.start()

    assert service._task is None
    assert service._evidence_task is None
