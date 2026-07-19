"""Tests for trigger_goal_stream_with_failure_policy SSOT."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus


@pytest.mark.asyncio
async def test_failure_policy_marks_needs_human_review():
    from app.services.agent.goal_stream_trigger import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-review",
        session_id="chat-1",
        objective="Build",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    with patch(
        "app.services.agent.goal_stream_trigger.trigger_goal_stream",
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
async def test_failure_policy_keep_active_skips_status_update():
    from app.services.agent.goal_stream_trigger import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-active",
        session_id="chat-2",
        objective="Loop",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    with patch(
        "app.services.agent.goal_stream_trigger.trigger_goal_stream",
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
async def test_failure_policy_success_returns_true():
    from app.services.agent.goal_stream_trigger import trigger_goal_stream_with_failure_policy

    goal = Goal(
        goal_id="g-ok",
        session_id="chat-3",
        objective="Run",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    with patch(
        "app.services.agent.goal_stream_trigger.trigger_goal_stream",
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
async def test_handle_unattended_goal_stream_failure_publishes_notification():
    from app.services.agent.goal_stream_trigger import handle_unattended_goal_stream_failure

    provider = AsyncMock()
    mock_bus = MagicMock()

    with (
        patch(
            "app.services.event.app_event_bus.get_event_bus",
            return_value=mock_bus,
        ),
        patch(
            "app.services.agent.goal_stream_trigger._resolve_user_locale",
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
async def test_runtime_stream_failure_invokes_failure_handler():
    import asyncio

    from app.services.agent.goal_stream_trigger import trigger_goal_stream

    goal = Goal(
        goal_id="g-runtime",
        session_id="chat-4",
        objective="Long run",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()

    async def failing_stream(_params: object) -> object:
        raise RuntimeError("mid stream")
        yield None  # pragma: no cover

    with (
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            failing_stream,
        ),
        patch(
            "app.services.agent.goal_stream_trigger.handle_unattended_goal_stream_failure",
            new_callable=AsyncMock,
        ) as mock_handle,
        patch(
            "app.ai_agents.GeneralAgentParams",
            side_effect=lambda **kwargs: MagicMock(**kwargs),
        ),
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
        ),
        patch(
            "app.core.channel_bridge.model_resolver.resolve_model_config",
            return_value={},
        ),
        patch(
            "app.core.channel_bridge.model_resolver.enrich_model_context_window",
            side_effect=lambda cfg, _: cfg,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_fallback_model_configs",
            return_value=(None, None),
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_retrieval_models",
            return_value=(None, None),
        ),
        patch(
            "app.core.channel_bridge.config_parsers.verify_search_service_available",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        await trigger_goal_stream(
            "chat-4",
            goal,
            provider=provider,
            on_failure="needs_human_review",
            context="runtime test",
        )
        await asyncio.sleep(0.05)

    mock_handle.assert_awaited_once_with(
        "chat-4",
        "g-runtime",
        provider,
        on_failure="needs_human_review",
        context="runtime test",
    )
