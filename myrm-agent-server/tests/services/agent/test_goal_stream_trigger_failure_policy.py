"""Tests for trigger_goal_stream_with_failure_policy SSOT."""

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus


def _goal(goal_id: str, status: GoalStatus) -> Goal:
    return Goal(goal_id=goal_id, session_id="chat-4", objective="Run", status=status, budget=GoalBudget(max_turns=5))


@pytest.mark.asyncio
async def test_failure_policy_marks_needs_human_review() -> None:
    from app.services.agent.goals.goal_stream_trigger import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-review",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()
    provider.get_goal.return_value = goal

    with patch(
        "app.services.agent.goals.goal_stream_trigger.trigger_goal_stream",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        ok = await trigger_goal_stream_with_failure_policy(
            "chat-1",
            goal,
            provider,
            on_failure="needs_human_review",
            context="test",
        )

    assert ok is False
    provider.update_status.assert_called_once_with("g-review", GoalStatus.NEEDS_HUMAN_REVIEW)


@pytest.mark.asyncio
async def test_failure_policy_keep_active_skips_status_update() -> None:
    from app.services.agent.goals.goal_stream_trigger import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-active",
        session_id="chat-2",
        objective="Loop",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    with patch(
        "app.services.agent.goals.goal_stream_trigger.trigger_goal_stream",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        ok = await trigger_goal_stream_with_failure_policy(
            "chat-2",
            goal,
            provider,
            on_failure="keep_active",
            context="loop restart",
        )

    assert ok is False
    provider.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_failure_policy_success_returns_true() -> None:
    from app.services.agent.goals.goal_stream_trigger import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-ok",
        session_id="chat-3",
        objective="Run",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    with patch(
        "app.services.agent.goals.goal_stream_trigger.trigger_goal_stream",
        new_callable=AsyncMock,
    ) as mock_trigger:
        ok = await trigger_goal_stream_with_failure_policy(
            "chat-3",
            goal,
            provider,
            on_failure="needs_human_review",
        )

    assert ok is True
    mock_trigger.assert_awaited_once()
    provider.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_handle_unattended_goal_stream_failure_publishes_notification() -> None:
    from app.services.agent.goals.unattended_goal_failure import handle_unattended_goal_stream_failure

    provider = AsyncMock()
    provider.get_goal.return_value = _goal("g-runtime", GoalStatus.ACTIVE)
    mock_bus = MagicMock()

    with (
        patch(
            "app.services.event.app_event_bus.get_event_bus",
            return_value=mock_bus,
        ),
        patch(
            "app.services.agent.goals.unattended_goal_failure.resolve_user_locale",
            new_callable=AsyncMock,
            return_value="en",
        ),
        patch(
            "app.channels.i18n.engine.channel_t",
            side_effect=lambda _locale, key: key,
        ),
    ):
        await handle_unattended_goal_stream_failure(
            "chat-4",
            "g-runtime",
            provider,
            on_failure="needs_human_review",
            context="runtime test",
        )

    provider.update_status.assert_called_once_with("g-runtime", GoalStatus.NEEDS_HUMAN_REVIEW)
    mock_bus.publish.assert_called_once()
    published = mock_bus.publish.call_args[0][0]
    assert published.data["meta_data"]["kind"] == "goal_needs_review"
    assert published.data["meta_data"]["chat_id"] == "chat-4"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [GoalStatus.WAIT, GoalStatus.PAUSED, GoalStatus.COMPLETE])
async def test_failure_after_the_run_moved_the_goal_on_keeps_that_state(status: GoalStatus) -> None:
    from app.services.agent.goals.unattended_goal_failure import handle_unattended_goal_stream_failure

    provider = AsyncMock()
    provider.get_goal.return_value = _goal("g-moved", status)

    with patch(
        "app.services.agent.goals.unattended_goal_failure.publish_goal_needs_review_notification",
        new_callable=AsyncMock,
    ) as publish:
        await handle_unattended_goal_stream_failure(
            "chat-4",
            "g-moved",
            provider,
            on_failure="needs_human_review",
            context="runtime test",
        )

    provider.update_status.assert_not_called()
    publish.assert_not_awaited()


def _runtime_goal() -> Goal:
    return Goal(
        goal_id="g-runtime",
        session_id="chat-4",
        objective="Long run",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )


@contextmanager
def _trigger_environment(stream: Callable[..., AsyncIterator[object]]) -> Iterator[AsyncMock]:
    """Everything ``trigger_goal_stream`` loads before it starts the headless stream, with ``stream`` as the agent.

    Yields the failure handler the stream's errors go to.
    """
    with ExitStack() as stack:
        stack.enter_context(patch("app.services.agent.streaming.ai_agent_service_stream", stream))
        handler = stack.enter_context(
            patch(
                "app.services.agent.goals.goal_stream_trigger.handle_unattended_goal_stream_failure",
                new_callable=AsyncMock,
            )
        )
        stack.enter_context(patch("app.ai_agents.GeneralAgentParams", side_effect=lambda **kwargs: MagicMock(**kwargs)))
        stack.enter_context(
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    providers_dict={},
                    retrieval_dict={},
                    security_config_dict={"yolo_mode_enabled": True},
                    search_cfg=None,
                    search_is_user_configured=False,
                ),
            )
        )
        stack.enter_context(
            patch(
                "app.core.channel_bridge.model_resolver.resolve_model_config",
                return_value=MagicMock(supports_vision=False, model="fake/test"),
            )
        )
        stack.enter_context(
            patch(
                "app.core.channel_bridge.model_resolver.enrich_model_capabilities",
                side_effect=lambda cfg, *_args, **_kwargs: cfg,
            )
        )
        stack.enter_context(
            patch("app.core.channel_bridge.model_resolver.enrich_model_context_window", side_effect=lambda cfg, _: cfg)
        )
        stack.enter_context(
            patch("app.core.channel_bridge.config_parsers.extract_fallback_model_configs", return_value=(None, None))
        )
        stack.enter_context(patch("app.core.channel_bridge.config_parsers.extract_retrieval_models", return_value=(None, None)))
        stack.enter_context(
            patch(
                "app.core.channel_bridge.config_parsers.verify_search_service_available",
                new_callable=AsyncMock,
                return_value=False,
            )
        )
        stack.enter_context(
            patch(
                "app.core.skills.gates.disabled_skill_roots.collect_disabled_skill_roots",
                new_callable=AsyncMock,
                return_value=[],
            )
        )
        yield handler


async def _run_headless_stream(goal: Goal, provider: AsyncMock) -> None:
    from app.services.agent.goals.goal_stream_trigger import trigger_goal_stream

    await trigger_goal_stream("chat-4", goal, provider=provider, on_failure="needs_human_review", context="runtime test")
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_runtime_stream_failure_invokes_failure_handler() -> None:
    provider = AsyncMock()

    async def failing_stream(_params: object, **_kwargs: object) -> AsyncIterator[object]:
        raise RuntimeError("mid stream")
        yield None  # pragma: no cover

    with _trigger_environment(failing_stream) as mock_handle:
        await _run_headless_stream(_runtime_goal(), provider)

    mock_handle.assert_awaited_once_with(
        "chat-4",
        "g-runtime",
        provider,
        on_failure="needs_human_review",
        context="runtime test",
    )


@pytest.mark.asyncio
async def test_a_stream_that_finds_the_session_taken_leaves_the_goal_to_the_turn_that_took_it() -> None:
    """A second start of the same goal, or a message sent while the start was loading, claims the session first."""
    from app.services.agent.gateway import AgentBusyError

    provider = AsyncMock()

    async def busy_stream(_params: object, **_kwargs: object) -> AsyncIterator[object]:
        raise AgentBusyError("Session chat-4 is already active")
        yield None  # pragma: no cover

    with _trigger_environment(busy_stream) as mock_handle:
        await _run_headless_stream(_runtime_goal(), provider)

    mock_handle.assert_not_awaited()
    provider.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_a_second_start_finds_the_gateway_session_taken_and_leaves_the_first_turn_running() -> None:
    """The busy signal is the real gateway's, and the turn that holds the session is not disturbed by the late start."""
    from app.services.agent.gateway import get_agent_gateway

    gate = asyncio.Event()

    async def held_events() -> AsyncGenerator[dict[str, object], None]:
        await gate.wait()
        yield {"type": "tick"}

    async def stream_through_gateway(_params: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        async for event in get_agent_gateway().execute_stream(held_events(), agent_type="general", session_id="chat-4"):
            yield event

    gateway = get_agent_gateway()
    with _trigger_environment(stream_through_gateway) as mock_handle:
        try:
            await _run_headless_stream(_runtime_goal(), AsyncMock())
            assert gateway.is_session_active("chat-4")

            await _run_headless_stream(_runtime_goal(), AsyncMock())

            mock_handle.assert_not_awaited()
            assert gateway.is_session_active("chat-4")
        finally:
            gate.set()
            await asyncio.sleep(0.05)

    assert not gateway.is_session_active("chat-4")
    mock_handle.assert_not_awaited()
