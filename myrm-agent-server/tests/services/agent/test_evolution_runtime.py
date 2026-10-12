"""Skill evolution runtime: startup prerequisites, proposal routing, shutdown."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.evolution import evolution_runtime


@pytest.fixture(autouse=True)
def _fresh_runtime() -> Iterator[None]:
    original = evolution_runtime._started_integration
    evolution_runtime._started_integration = None
    yield
    evolution_runtime._started_integration = original


@contextmanager
def _startup_environment(integration: MagicMock) -> Iterator[tuple[MagicMock, MagicMock]]:
    """Patch every startup dependency; yields (screener_cls, integration_factory)."""
    llm_manager = MagicMock()
    llm_manager.get_llm_from_config = AsyncMock(return_value=MagicMock())
    integration_factory = MagicMock(return_value=integration)
    with ExitStack() as stack:
        stack.enter_context(patch.object(evolution_runtime, "get_global_evolution_integration", return_value=None))
        stack.enter_context(patch.object(evolution_runtime, "llm_manager", llm_manager))
        stack.enter_context(
            patch.object(
                evolution_runtime,
                "load_platform_evolution_model_config",
                new=AsyncMock(return_value=SimpleNamespace()),
            )
        )
        stack.enter_context(
            patch.object(
                evolution_runtime,
                "load_user_configs",
                new=AsyncMock(return_value=SimpleNamespace(search_cfg=None, search_is_user_configured=False)),
            )
        )
        screener_cls = stack.enter_context(patch.object(evolution_runtime, "EvolutionScreener"))
        stack.enter_context(patch.object(evolution_runtime, "EvolutionIntegration", integration_factory))
        yield screener_cls, integration_factory


@pytest.mark.asyncio
async def test_runtime_starts_with_evolution_model_only() -> None:
    integration = MagicMock()
    integration.start_background_queue = AsyncMock()
    embedding_requirement = AsyncMock(side_effect=RuntimeError("embedding must not be required"))

    with (
        patch("app.services.agent.platform_config.require_platform_embedding_config", new=embedding_requirement),
        _startup_environment(integration) as (screener_cls, integration_factory),
    ):
        await evolution_runtime.init_evolution_runtime()

    integration_factory.assert_called_once()
    assert "vector_store" not in integration_factory.call_args.kwargs
    assert "embedding" not in integration_factory.call_args.kwargs
    embedding_requirement.assert_not_awaited()
    assert screener_cls.call_args.kwargs["store"] is integration.store
    assert integration.screener is screener_cls.return_value
    integration.start_background_queue.assert_awaited_once_with(on_proposal_callback=evolution_runtime.handle_new_proposal)
    assert evolution_runtime._started_integration is integration


@pytest.mark.asyncio
async def test_runtime_is_disabled_without_evolution_model() -> None:
    integration_factory = MagicMock()

    with (
        patch.object(evolution_runtime, "get_global_evolution_integration", return_value=None),
        patch.object(
            evolution_runtime,
            "load_platform_evolution_model_config",
            new=AsyncMock(side_effect=RuntimeError("not configured")),
        ),
        patch.object(evolution_runtime, "EvolutionIntegration", integration_factory),
    ):
        await evolution_runtime.init_evolution_runtime()

    integration_factory.assert_not_called()
    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
async def test_runtime_leaves_an_existing_global_integration_alone() -> None:
    integration_factory = MagicMock()

    with (
        patch.object(evolution_runtime, "get_global_evolution_integration", return_value=MagicMock()),
        patch.object(evolution_runtime, "EvolutionIntegration", integration_factory),
    ):
        await evolution_runtime.init_evolution_runtime()

    integration_factory.assert_not_called()
    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
async def test_shutdown_stops_the_queue_it_started() -> None:
    integration = MagicMock()
    integration.stop_background_queue = AsyncMock()
    evolution_runtime._started_integration = integration

    await evolution_runtime.shutdown_evolution_runtime()

    integration.stop_background_queue.assert_awaited_once()
    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
async def test_shutdown_without_started_runtime_is_a_noop() -> None:
    await evolution_runtime.shutdown_evolution_runtime()

    assert evolution_runtime._started_integration is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approved", "expected_channel"),
    [(True, "message"), (False, "proposal")],
)
async def test_proposal_is_routed_by_approval_result(approved: bool, expected_channel: str) -> None:
    proposal = MagicMock(skill_id="s1", score=0.9)
    proposal.to_dict.return_value = {"skill_id": "s1"}
    flow = MagicMock()
    flow.process_evolution = AsyncMock(return_value=SimpleNamespace(approved=approved))
    broadcast_message = AsyncMock()
    broadcast_proposal = AsyncMock()

    with (
        patch.object(evolution_runtime, "ConfidenceApprovalFlow", MagicMock(return_value=flow)),
        patch.object(evolution_runtime, "broadcast_message", broadcast_message),
        patch.object(evolution_runtime, "broadcast_proposal", broadcast_proposal),
    ):
        await evolution_runtime.handle_new_proposal(proposal)

    if expected_channel == "message":
        broadcast_message.assert_awaited_once_with("AUTO_MERGED_EVOLUTION", {"skill_id": "s1"})
        broadcast_proposal.assert_not_awaited()
    else:
        broadcast_proposal.assert_awaited_once_with({"skill_id": "s1"})
        broadcast_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_proposal_is_not_broadcast_when_persistence_fails() -> None:
    proposal = MagicMock(skill_id="s1", score=0.9)
    flow = MagicMock()
    flow.process_evolution = AsyncMock(side_effect=RuntimeError("db down"))
    broadcast_message = AsyncMock()
    broadcast_proposal = AsyncMock()

    with (
        patch.object(evolution_runtime, "ConfidenceApprovalFlow", MagicMock(return_value=flow)),
        patch.object(evolution_runtime, "broadcast_message", broadcast_message),
        patch.object(evolution_runtime, "broadcast_proposal", broadcast_proposal),
    ):
        await evolution_runtime.handle_new_proposal(proposal)

    broadcast_message.assert_not_awaited()
    broadcast_proposal.assert_not_awaited()
