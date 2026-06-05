"""Tests for goal_learnings module — server-layer callback and retrieval logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from myrm_agent_harness.agent.goals.types import GoalExecutionSummary

from app.ai_agents.general_agent.goal_learnings import (
    build_goal_terminal_callback,
    retrieve_relevant_learnings,
)


def _make_summary(**overrides: object) -> GoalExecutionSummary:
    defaults = {
        "files_modified": (),
        "verifications": (),
        "browser_checks": 0,
        "total_tokens": 100,
        "total_cost_usd": 0.01,
        "execution_duration_s": 5.0,
        "turns_used": 2,
    }
    defaults.update(overrides)
    return GoalExecutionSummary(**defaults)


class TestBuildGoalTerminalCallback:
    """Test the on_goal_terminal callback factory."""

    @pytest.mark.asyncio
    async def test_callback_extracts_and_stores_learnings(self):
        """Callback should extract learnings and persist them."""
        memory_manager = AsyncMock()
        llm = MagicMock()

        with (
            patch("myrm_agent_harness.agent._internals.memory_extraction.create_extraction_llm_func") as mock_create_llm,
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_goal_learnings",
                new_callable=AsyncMock,
            ) as mock_extract,
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.persist_extracted_memories",
                new_callable=AsyncMock,
            ) as mock_persist,
        ):
            mock_llm_func = AsyncMock()
            mock_create_llm.return_value = mock_llm_func
            mock_extract.return_value = [
                MagicMock(memory_type="semantic", content="Always check tests"),
            ]
            mock_persist.return_value = 1

            callback = build_goal_terminal_callback(memory_manager, llm)

            goal = MagicMock()
            goal.goal_id = "goal-123"
            goal.objective = "Add authentication"
            goal.session_id = "session-1"

            messages = [
                HumanMessage(content="Add JWT auth"),
                AIMessage(content="I'll implement JWT authentication..."),
                HumanMessage(content="Good, also add refresh tokens"),
                AIMessage(content="Done! Implemented refresh token rotation."),
            ]

            await callback(goal, messages, _make_summary())

            mock_create_llm.assert_called_once_with(llm)
            mock_extract.assert_called_once()
            mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_callback_skips_with_few_messages(self):
        """Callback should skip when too few messages."""
        memory_manager = AsyncMock()
        llm = MagicMock()

        callback = build_goal_terminal_callback(memory_manager, llm)

        goal = MagicMock()
        goal.goal_id = "goal-123"
        goal.objective = "Quick task"

        messages = [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello!"),
        ]

        await callback(goal, messages, _make_summary())
        memory_manager.store_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_callback_handles_llm_failure_gracefully(self):
        """Callback should not raise on LLM failure."""
        memory_manager = AsyncMock()
        llm = MagicMock()

        with (
            patch("myrm_agent_harness.agent._internals.memory_extraction.create_extraction_llm_func") as mock_create_llm,
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_goal_learnings",
                new_callable=AsyncMock,
                side_effect=RuntimeError("API error"),
            ),
        ):
            mock_create_llm.return_value = AsyncMock()

            callback = build_goal_terminal_callback(memory_manager, llm)

            goal = MagicMock()
            goal.goal_id = "goal-123"
            goal.objective = "Complex task"
            goal.session_id = "session-1"

            messages = [
                HumanMessage(content="Do A"),
                AIMessage(content="Doing A..."),
                HumanMessage(content="Now B"),
                AIMessage(content="Done B."),
            ]

            # Should not raise
            await callback(goal, messages, _make_summary())


class TestGoalTerminalEventPublishing:
    """Test GOAL_TERMINAL event publishing in on_goal_terminal callback."""

    @pytest.mark.asyncio
    async def test_publishes_goal_terminal_event(self):
        """Callback should publish GOAL_TERMINAL to EventBus."""
        memory_manager = AsyncMock()
        llm = MagicMock()

        with patch("app.services.event.app_event_bus.get_event_bus") as mock_get_bus:
            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            callback = build_goal_terminal_callback(memory_manager, llm)

            goal = MagicMock()
            goal.goal_id = "goal-evt-1"
            goal.session_id = "session-evt"
            goal.objective = "Test event publishing"
            goal.status.value = "complete"

            summary = _make_summary(
                files_modified=("a.py", "b.py"),
                total_tokens=5000,
                total_cost_usd=0.25,
            )

            await callback(goal, [HumanMessage(content="x"), AIMessage(content="y")], summary)

            mock_bus.publish.assert_called_once()
            event = mock_bus.publish.call_args[0][0]
            assert event.event_type.value == "goal_terminal"
            assert event.data["goal_id"] == "goal-evt-1"
            assert event.data["session_id"] == "session-evt"
            assert event.data["status"] == "complete"
            assert event.data["objective"] == "Test event publishing"
            assert event.data["files_modified"] == 2
            assert event.data["total_tokens"] == 5000
            assert event.data["total_cost_usd"] == 0.25

    @pytest.mark.asyncio
    async def test_event_publish_failure_non_fatal(self):
        """EventBus publish failure should not prevent learnings extraction."""
        memory_manager = AsyncMock()
        llm = MagicMock()

        with (
            patch(
                "app.services.event.app_event_bus.get_event_bus",
                side_effect=RuntimeError("EventBus unavailable"),
            ),
            patch("myrm_agent_harness.agent._internals.memory_extraction.create_extraction_llm_func") as mock_create_llm,
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.extractor.extract_goal_learnings",
                new_callable=AsyncMock,
            ) as mock_extract,
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.persist_extracted_memories",
                new_callable=AsyncMock,
            ) as mock_persist,
        ):
            mock_create_llm.return_value = AsyncMock()
            mock_extract.return_value = [
                MagicMock(memory_type="semantic", content="A valuable learning"),
            ]
            mock_persist.return_value = 1

            callback = build_goal_terminal_callback(memory_manager, llm)

            goal = MagicMock()
            goal.goal_id = "goal-evt-2"
            goal.session_id = "session-evt"
            goal.objective = "Test resilience"
            goal.status.value = "complete"

            messages = [
                HumanMessage(content="Do X"),
                AIMessage(content="Doing X..."),
                HumanMessage(content="Continue"),
                AIMessage(content="Done X."),
            ]

            await callback(goal, messages, _make_summary())
            mock_extract.assert_called_once()
            mock_persist.assert_called_once()

    @pytest.mark.asyncio
    async def test_objective_truncated_in_event(self):
        """Long objectives should be truncated to 200 chars in event data."""
        memory_manager = AsyncMock()
        llm = MagicMock()

        with patch("app.services.event.app_event_bus.get_event_bus") as mock_get_bus:
            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            callback = build_goal_terminal_callback(memory_manager, llm)

            goal = MagicMock()
            goal.goal_id = "goal-trunc"
            goal.session_id = "session-trunc"
            goal.objective = "A" * 500
            goal.status.value = "budget_limited"

            await callback(goal, [HumanMessage(content="x"), AIMessage(content="y")], _make_summary())

            event = mock_bus.publish.call_args[0][0]
            assert len(event.data["objective"]) == 200


class TestGoalTerminalNotificationTemplate:
    """Test dispatcher template formatting for GOAL_TERMINAL events."""

    def test_goal_terminal_template_format(self):
        from app.core.notifications.dispatcher import _format_message
        from app.services.event.app_event_bus import AppEvent, AppEventType

        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "status": "complete",
                "objective": "Refactor auth module",
                "files_modified": 3,
                "total_tokens": 5000,
                "total_cost_usd": 0.25,
            },
        )
        result = _format_message(event)
        assert result == "[Myrm AI] Goal complete: Refactor auth module\n3 files · 5,000 tokens · $0.25"

    def test_goal_terminal_template_budget_limited(self):
        from app.core.notifications.dispatcher import _format_message
        from app.services.event.app_event_bus import AppEvent, AppEventType

        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "status": "budget_limited",
                "objective": "Long task",
                "files_modified": 0,
                "total_tokens": 10000,
                "total_cost_usd": 1.50,
            },
        )
        result = _format_message(event)
        assert result == "[Myrm AI] Goal budget_limited: Long task\n0 files · 10,000 tokens · $1.50"


class TestRetrieveRelevantLearnings:
    """Test historical learnings retrieval."""

    @pytest.mark.asyncio
    async def test_retrieves_relevant_learnings(self):
        """Should return content from search results."""
        memory_manager = AsyncMock()
        result1 = MagicMock()
        result1.content = "Always check locale files after i18n changes"
        result2 = MagicMock()
        result2.content = "Use bun instead of npm in this project"
        memory_manager.search.return_value = [result1, result2]

        learnings = await retrieve_relevant_learnings(memory_manager, "Add i18n support to settings page")

        assert len(learnings) == 2
        assert "locale files" in learnings[0]
        assert "bun" in learnings[1]
        memory_manager.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_on_search_failure(self):
        """Should return empty list on failure."""
        memory_manager = AsyncMock()
        memory_manager.search.side_effect = RuntimeError("DB connection lost")

        learnings = await retrieve_relevant_learnings(memory_manager, "Add feature X")

        assert learnings == []

    @pytest.mark.asyncio
    async def test_filters_short_content(self):
        """Should filter out very short results."""
        memory_manager = AsyncMock()
        result1 = MagicMock()
        result1.content = "OK"
        result2 = MagicMock()
        result2.content = "Always validate input before processing database queries"
        memory_manager.search.return_value = [result1, result2]

        learnings = await retrieve_relevant_learnings(memory_manager, "Database operations")

        assert len(learnings) == 1
        assert "validate input" in learnings[0]

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """Should respect the limit parameter."""
        memory_manager = AsyncMock()
        results = [MagicMock(content=f"Learning number {i} is important") for i in range(10)]
        memory_manager.search.return_value = results

        learnings = await retrieve_relevant_learnings(memory_manager, "test", limit=3)

        assert len(learnings) == 3


class TestTryDequeueNext:
    """Test the _try_dequeue_next auto-serial execution logic."""

    @pytest.mark.asyncio
    async def test_dequeues_and_triggers_stream_on_success(self):
        """When queue has a goal, dequeue it and trigger a new stream."""
        mock_goal = MagicMock()
        mock_goal.goal_id = "goal-dequeue-1"
        mock_goal.objective = "Next task"

        mock_provider = AsyncMock()
        mock_provider.dequeue_next.return_value = mock_goal

        mock_registry = MagicMock()
        mock_registry.get_provider.return_value = mock_provider

        with (
            patch(
                "app.services.agent.goal_registry.GoalRegistry",
                mock_registry,
            ),
            patch(
                "app.services.agent.goal_stream_trigger.trigger_goal_stream",
                new_callable=AsyncMock,
            ) as mock_trigger,
            patch("app.services.event.app_event_bus.get_event_bus") as mock_get_bus,
        ):
            mock_get_bus.return_value = MagicMock()

            from app.ai_agents.general_agent.goal_learnings import _try_dequeue_next

            await _try_dequeue_next("session-dq-1")

            mock_provider.dequeue_next.assert_called_once_with("session-dq-1")
            mock_trigger.assert_called_once_with("session-dq-1", mock_goal)

    @pytest.mark.asyncio
    async def test_does_nothing_when_queue_empty(self):
        """When queue is empty, no stream is triggered."""
        mock_provider = AsyncMock()
        mock_provider.dequeue_next.return_value = None

        mock_registry = MagicMock()
        mock_registry.get_provider.return_value = mock_provider

        with (
            patch(
                "app.services.agent.goal_registry.GoalRegistry",
                mock_registry,
            ),
            patch(
                "app.services.agent.goal_stream_trigger.trigger_goal_stream",
                new_callable=AsyncMock,
            ) as mock_trigger,
        ):
            from app.ai_agents.general_agent.goal_learnings import _try_dequeue_next

            await _try_dequeue_next("session-empty")

            mock_trigger.assert_not_called()

    @pytest.mark.asyncio
    async def test_respects_depth_limit(self):
        """Should not recurse beyond depth=5."""
        from app.ai_agents.general_agent.goal_learnings import _try_dequeue_next

        with patch(
            "app.services.agent.goal_registry.GoalRegistry",
        ) as mock_registry:
            await _try_dequeue_next("session-deep", _depth=5)
            mock_registry.get_provider.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_nothing_when_no_provider(self):
        """When no GoalProvider registered for session, does nothing."""
        mock_registry = MagicMock()
        mock_registry.get_provider.return_value = None

        with (
            patch(
                "app.services.agent.goal_registry.GoalRegistry",
                mock_registry,
            ),
            patch(
                "app.services.agent.goal_stream_trigger.trigger_goal_stream",
                new_callable=AsyncMock,
            ) as mock_trigger,
        ):
            from app.ai_agents.general_agent.goal_learnings import _try_dequeue_next

            await _try_dequeue_next("session-no-provider")

            mock_trigger.assert_not_called()
