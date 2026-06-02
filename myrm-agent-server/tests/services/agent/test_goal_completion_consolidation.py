"""Goal completion → SharedContext consolidation tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.sub_agents.planner.schemas import DecisionRecord, Plan

from app.services.agent.goal_registry import ServerGoalManager


def _sample_plan() -> Plan:
    return Plan(
        goal="Ship launch doc",
        reasoning="Structured approach",
        steps=[],
        decisions=[
            DecisionRecord(
                topic="Database",
                decision="Use PostgreSQL",
                rationale="Team standard",
                status="active",
            )
        ],
    )


def _sample_goal(session_id: str = "chat-1", goal_id: str = "goal-1") -> SimpleNamespace:
    return SimpleNamespace(session_id=session_id, goal_id=goal_id)


@pytest.fixture
def manager() -> ServerGoalManager:
    return ServerGoalManager(AsyncMock())


class TestGoalCompletionConsolidation:
    @pytest.mark.asyncio
    async def test_auto_approve_materializes_proposal(self, manager: ServerGoalManager) -> None:
        plan = _sample_plan()
        goal = _sample_goal()
        context = SimpleNamespace(
            id="ctx-1",
            name="Team Memory",
            status="active",
            policy={"goal_completion_auto_approve": True},
        )
        proposal = SimpleNamespace(id="proposal-1", status="pending")

        mock_service = AsyncMock()
        mock_service.get_context.return_value = context
        mock_service.create_write_proposal.return_value = proposal

        mock_materializer = AsyncMock()
        mock_materializer.approve_write_proposal.return_value = proposal

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_factory = MagicMock(return_value=mock_session)

        mock_event_bus = MagicMock()

        with (
            patch(
                "myrm_agent_harness.agent.sub_agents.planner.storage.PlannerStorage"
            ) as planner_cls,
            patch(
                "app.services.agent.goal_registry._resolve_shared_context_ids_for_goal",
                new=AsyncMock(return_value=["ctx-1"]),
            ),
            patch(
                "app.platform_utils.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "app.services.memory.shared_context.SharedContextService",
                return_value=mock_service,
            ),
            patch(
                "app.services.memory.shared_context_materializer.SharedContextProposalMaterializer",
                return_value=mock_materializer,
            ),
            patch(
                "app.services.event.app_event_bus.get_event_bus",
                return_value=mock_event_bus,
            ),
        ):
            planner_cls.return_value.load_plan = AsyncMock(return_value=plan)
            await manager._consolidate_decisions_on_completion(goal)

        planner_cls.assert_called_once_with(manager._storage._storage, prefix="planner_")
        mock_materializer.approve_write_proposal.assert_awaited_once_with("proposal-1")
        mock_event_bus.publish.assert_called_once()
        event_payload = mock_event_bus.publish.call_args[0][0].data
        assert event_payload["operation"] == "goal_completion_consolidation"
        assert event_payload["auto_approved"] is True
        assert event_payload["decision_count"] == 1

    @pytest.mark.asyncio
    async def test_pending_when_auto_approve_disabled(self, manager: ServerGoalManager) -> None:
        plan = _sample_plan()
        goal = _sample_goal()
        context = SimpleNamespace(
            id="ctx-1",
            name="Team Memory",
            status="active",
            policy={"goal_completion_auto_approve": False},
        )
        proposal = SimpleNamespace(id="proposal-1", status="pending")

        mock_service = AsyncMock()
        mock_service.get_context.return_value = context
        mock_service.create_write_proposal.return_value = proposal

        mock_materializer = AsyncMock()
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_factory = MagicMock(return_value=mock_session)

        with (
            patch(
                "myrm_agent_harness.agent.sub_agents.planner.storage.PlannerStorage"
            ) as planner_cls,
            patch(
                "app.services.agent.goal_registry._resolve_shared_context_ids_for_goal",
                new=AsyncMock(return_value=["ctx-1"]),
            ),
            patch(
                "app.platform_utils.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "app.services.memory.shared_context.SharedContextService",
                return_value=mock_service,
            ),
            patch(
                "app.services.memory.shared_context_materializer.SharedContextProposalMaterializer",
                return_value=mock_materializer,
            ),
            patch("app.services.event.app_event_bus.get_event_bus", return_value=MagicMock()),
        ):
            planner_cls.return_value.load_plan = AsyncMock(return_value=plan)
            await manager._consolidate_decisions_on_completion(goal)

        mock_materializer.approve_write_proposal.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_auto_approve_when_policy_key_missing(self, manager: ServerGoalManager) -> None:
        plan = _sample_plan()
        goal = _sample_goal()
        context = SimpleNamespace(
            id="ctx-1",
            name="Team Memory",
            status="active",
            policy={},
        )
        proposal = SimpleNamespace(id="proposal-1", status="pending")

        mock_service = AsyncMock()
        mock_service.get_context.return_value = context
        mock_service.create_write_proposal.return_value = proposal

        mock_materializer = AsyncMock()
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_factory = MagicMock(return_value=mock_session)

        with (
            patch(
                "myrm_agent_harness.agent.sub_agents.planner.storage.PlannerStorage"
            ) as planner_cls,
            patch(
                "app.services.agent.goal_registry._resolve_shared_context_ids_for_goal",
                new=AsyncMock(return_value=["ctx-1"]),
            ),
            patch(
                "app.platform_utils.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "app.services.memory.shared_context.SharedContextService",
                return_value=mock_service,
            ),
            patch(
                "app.services.memory.shared_context_materializer.SharedContextProposalMaterializer",
                return_value=mock_materializer,
            ),
            patch("app.services.event.app_event_bus.get_event_bus", return_value=MagicMock()),
        ):
            planner_cls.return_value.load_plan = AsyncMock(return_value=plan)
            await manager._consolidate_decisions_on_completion(goal)

        mock_materializer.approve_write_proposal.assert_awaited_once_with("proposal-1")

    @pytest.mark.asyncio
    async def test_skips_when_no_shared_context_binding(
        self, manager: ServerGoalManager
    ) -> None:
        plan = _sample_plan()
        goal = _sample_goal()

        with (
            patch(
                "myrm_agent_harness.agent.sub_agents.planner.storage.PlannerStorage"
            ) as planner_cls,
            patch(
                "app.services.agent.goal_registry._resolve_shared_context_ids_for_goal",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.platform_utils.get_session_factory",
            ) as session_factory_patch,
        ):
            planner_cls.return_value.load_plan = AsyncMock(return_value=plan)
            await manager._consolidate_decisions_on_completion(goal)

        session_factory_patch.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotent_skip_when_proposal_already_approved(
        self, manager: ServerGoalManager
    ) -> None:
        plan = _sample_plan()
        goal = _sample_goal()
        context = SimpleNamespace(
            id="ctx-1",
            name="Team Memory",
            status="active",
            policy={"goal_completion_auto_approve": True},
        )
        proposal = SimpleNamespace(id="proposal-1", status="approved")

        mock_service = AsyncMock()
        mock_service.get_context.return_value = context
        mock_service.create_write_proposal.return_value = proposal

        mock_materializer = AsyncMock()
        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.__aexit__.return_value = None
        mock_session_factory = MagicMock(return_value=mock_session)
        mock_event_bus = MagicMock()

        with (
            patch(
                "myrm_agent_harness.agent.sub_agents.planner.storage.PlannerStorage"
            ) as planner_cls,
            patch(
                "app.services.agent.goal_registry._resolve_shared_context_ids_for_goal",
                new=AsyncMock(return_value=["ctx-1"]),
            ),
            patch(
                "app.platform_utils.get_session_factory",
                return_value=mock_session_factory,
            ),
            patch(
                "app.services.memory.shared_context.SharedContextService",
                return_value=mock_service,
            ),
            patch(
                "app.services.memory.shared_context_materializer.SharedContextProposalMaterializer",
                return_value=mock_materializer,
            ),
            patch(
                "app.services.event.app_event_bus.get_event_bus",
                return_value=mock_event_bus,
            ),
        ):
            planner_cls.return_value.load_plan = AsyncMock(return_value=plan)
            await manager._consolidate_decisions_on_completion(goal)

        mock_materializer.approve_write_proposal.assert_not_awaited()
        mock_event_bus.publish.assert_not_called()


class TestResolveSharedContextForGoal:
    @pytest.mark.asyncio
    async def test_resolve_passes_agent_and_conversation(self) -> None:
        from app.services.agent.goal_registry import _resolve_shared_context_ids_for_goal

        chat = SimpleNamespace(agent_id="agent-42")
        with (
            patch(
                "app.services.chat.chat_service.ChatService.get_chat_metadata",
                new=AsyncMock(return_value=chat),
            ),
            patch(
                "app.services.memory.shared_context.resolve_shared_context_ids",
                new=AsyncMock(return_value=["ctx-1"]),
            ) as resolve_mock,
        ):
            result = await _resolve_shared_context_ids_for_goal("chat-99")

        assert result == ["ctx-1"]
        resolve_mock.assert_awaited_once_with(
            agent_id="agent-42",
            channel_id="web_chat",
            conversation_id="chat-99",
        )


class TestDefaultPolicy:
    def test_goal_completion_auto_approve_in_default_policy(self) -> None:
        from app.services.memory.shared_context import _DEFAULT_POLICY

        assert "goal_completion_auto_approve" in _DEFAULT_POLICY
        assert _DEFAULT_POLICY["goal_completion_auto_approve"] is True
