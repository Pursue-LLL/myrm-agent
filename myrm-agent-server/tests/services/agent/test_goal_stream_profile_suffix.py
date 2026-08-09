"""Goal stream continuation must inherit chat-bound profile context."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.goals.types import Goal, GoalBudget, GoalStatus

from app.services.agent.goal_stream_trigger import (
    GoalStreamAgentContext,
    _resolve_goal_stream_agent_context,
    trigger_goal_stream,
)
from app.services.agent.profile_resolver import ResolvedAgentProfile


@pytest.mark.asyncio
async def test_resolve_goal_stream_agent_context_applies_ko_formal_suffix() -> None:
    chat = MagicMock()
    chat.agent_id = "builtin-ko-office"

    profile = ResolvedAgentProfile(
        agent_id="builtin-ko-office",
        skill_ids=("skill-a",),
        mcp_ids=(),
        enabled_builtin_tools=("web_search",),
        system_prompt="Office assistant base prompt",
        engine_params={
            "response_locale_policy": {
                "locale": "ko-KR",
                "formality": "formal-polite",
            }
        },
    )

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=profile)

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=chat,
        ),
        patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
    ):
        ctx = await _resolve_goal_stream_agent_context("chat-session-1")

    assert ctx == GoalStreamAgentContext(
        agent_id="builtin-ko-office",
        user_instructions=ctx.user_instructions,
        subagent_ids=None,
        agent_skill_ids=["skill-a"],
        enabled_builtin_tools=["web_search"],
    )
    assert ctx.user_instructions is not None
    assert ctx.user_instructions.startswith("Office assistant base prompt")
    assert "합니다" in ctx.user_instructions
    mock_resolver.resolve.assert_awaited_once_with("builtin-ko-office")


@pytest.mark.asyncio
async def test_resolve_goal_stream_agent_context_team_includes_protocol_and_subagents() -> (
    None
):
    chat = MagicMock()
    chat.agent_id = "team-leader-1"

    profile = ResolvedAgentProfile(
        agent_id="team-leader-1",
        agent_type="team",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=("web_search",),
        subagent_ids=("sub-1", "sub-2"),
        system_prompt="Team leader base",
    )

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=profile)

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=chat,
        ),
        patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch(
            "app.ai_agents.team_protocol.build_leader_protocol_prompt",
            new_callable=AsyncMock,
            return_value="<team_leader_protocol>roster block</team_leader_protocol>",
        ) as mock_protocol,
    ):
        ctx = await _resolve_goal_stream_agent_context("chat-session-team")

    assert ctx.agent_id == "team-leader-1"
    assert ctx.subagent_ids == ["sub-1", "sub-2"]
    assert ctx.user_instructions is not None
    assert "Team leader base" in ctx.user_instructions
    assert "<team_leader_protocol>" in ctx.user_instructions
    mock_protocol.assert_awaited_once_with(
        ["sub-1", "sub-2"],
        leader_id="team-leader-1",
        dynamic_discovery=True,
    )


@pytest.mark.asyncio
async def test_resolve_goal_stream_agent_context_no_chat_agent() -> None:
    with patch(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
        return_value=None,
    ):
        ctx = await _resolve_goal_stream_agent_context("chat-session-2")

    assert ctx == GoalStreamAgentContext()


@pytest.mark.asyncio
async def test_trigger_goal_stream_injects_profile_into_general_agent_params() -> None:
    """Full trigger path: resolved profile fields must reach GeneralAgentParams."""
    goal = Goal(
        goal_id="g-ko",
        session_id="chat-ko-1",
        objective="Continue with formal Korean",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    agent_ctx = GoalStreamAgentContext(
        agent_id="builtin-ko-office",
        user_instructions="Base prompt\n\n[formal suffix with 합니다]",
        subagent_ids=None,
        agent_skill_ids=["skill-a"],
        enabled_builtin_tools=["web_search", "render_ui", "structured_clarify"],
        agent_security_raw={"capabilities": ["file_read"]},
    )
    captured: dict[str, object] = {}

    async def empty_stream(_params: object) -> object:
        if False:
            yield None

    def capture_params(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock(**kwargs)

    with (
        patch(
            "app.services.agent.goal_stream_trigger._resolve_goal_stream_agent_context",
            new_callable=AsyncMock,
            return_value=agent_ctx,
        ),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            empty_stream,
        ),
        patch(
            "app.ai_agents.GeneralAgentParams",
            side_effect=capture_params,
        ),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=MagicMock(
                providers_dict={},
                retrieval_dict={},
                security_config_dict={"yolo_mode_enabled": True},
                personal_settings_dict={"locale": "ko-KR"},
                search_cfg=None,
                search_is_user_configured=False,
            ),
        ),
        patch(
            "app.core.channel_bridge.model_resolver.resolve_model_config",
            return_value=MagicMock(supports_vision=False, model="fake/test"),
        ),
        patch(
            "app.core.channel_bridge.model_resolver.enrich_model_capabilities",
            side_effect=lambda cfg, *_args, **_kwargs: cfg,
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
        patch(
            "app.core.channel_bridge.config_parsers.resolve_vision_fallback_chain_for_agent",
            return_value=(None, []),
        ),
        patch(
            "app.core.skills.disabled_skill_roots.collect_disabled_skill_roots",
            new_callable=AsyncMock,
            return_value=[],
        ),
    ):
        await trigger_goal_stream("chat-ko-1", goal)
        await asyncio.sleep(0.05)

    assert captured.get("agent_id") == "builtin-ko-office"
    assert captured.get("chat_id") == "chat-ko-1"
    assert captured.get("query") == "Continue with formal Korean"
    assert captured.get("agent_skill_ids") == ["skill-a"]
    assert captured.get("subagent_ids") is None
    instructions = captured.get("user_instructions")
    assert isinstance(instructions, str)
    assert "합니다" in instructions
    assert captured.get("unattended_mode") is True
    assert captured.get("web_search_profile_enabled") is True
    assert captured.get("enable_render_ui") is True
    assert captured.get("enable_structured_clarify") is True
    assert captured.get("enable_shell_tools") is True
    file_access_mode = captured.get("file_access_mode")
    assert file_access_mode is not None
    assert getattr(file_access_mode, "value", file_access_mode) == "full"
    assert captured.get("agent_security_raw") == {"capabilities": ["file_read"]}
    assert captured.get("enable_web_fetch") is False
    assert captured.get("enable_memory") is False  # enableMemory unset → disabled


@pytest.mark.asyncio
async def test_trigger_goal_stream_injects_goal_provider_and_memory_switch() -> None:
    """GoalProvider must reach the stream via extra_context; enable_memory follows user switch."""
    goal = Goal(
        goal_id="g-provider",
        session_id="chat-provider-1",
        objective="Continue with goal lifecycle",
        status=GoalStatus.ACTIVE,
        budget=GoalBudget(max_turns=5),
    )
    provider = AsyncMock()
    agent_ctx = GoalStreamAgentContext(
        agent_id=None,
        user_instructions=None,
        subagent_ids=None,
        agent_skill_ids=[],
        enabled_builtin_tools=None,
        agent_security_raw=None,
    )
    captured_params: dict[str, object] = {}
    stream_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def capturing_stream(
        *_args: object, **_kwargs: object
    ) -> AsyncGenerator[object, None]:
        stream_calls.append((_args, _kwargs))
        if False:
            yield None

    def capture_params(**kwargs: object) -> MagicMock:
        captured_params.update(kwargs)
        return MagicMock(**kwargs)

    with (
        patch(
            "app.services.agent.goal_stream_trigger._resolve_goal_stream_agent_context",
            new_callable=AsyncMock,
            return_value=agent_ctx,
        ),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            capturing_stream,
        ),
        patch(
            "app.ai_agents.GeneralAgentParams",
            side_effect=capture_params,
        ),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=MagicMock(
                providers_dict={},
                retrieval_dict={},
                security_config_dict={"yolo_mode_enabled": True},
                personal_settings_dict={"enableMemory": True},
                search_cfg=None,
                search_is_user_configured=False,
            ),
        ),
        patch(
            "app.core.channel_bridge.model_resolver.resolve_model_config",
            return_value=MagicMock(supports_vision=False, model="fake/test"),
        ),
        patch(
            "app.core.channel_bridge.model_resolver.enrich_model_capabilities",
            side_effect=lambda cfg, *_args, **_kwargs: cfg,
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
        patch(
            "app.core.channel_bridge.config_parsers.resolve_vision_fallback_chain_for_agent",
            return_value=(None, []),
        ),
        patch(
            "app.core.skills.disabled_skill_roots.collect_disabled_skill_roots",
            new_callable=AsyncMock,
            return_value=["skills/prebuilt/off"],
        ),
    ):
        await trigger_goal_stream("chat-provider-1", goal, provider=provider)
        await asyncio.sleep(0.05)

    assert captured_params.get("enable_memory") is True  # enableMemory=True → enabled
    assert len(stream_calls) == 1
    _, stream_kwargs = stream_calls[0]
    extra_context = stream_kwargs.get("extra_context")
    assert isinstance(extra_context, dict)
    assert extra_context["goal_provider"] is provider
    assert extra_context["execution_mode"] == "pooled"
    assert extra_context["disabled_skill_roots"] == ["skills/prebuilt/off"]


@pytest.mark.asyncio
async def test_resolve_goal_stream_agent_context_loads_security_overrides() -> None:
    chat = MagicMock()
    chat.agent_id = "agent-sec-1"

    profile = ResolvedAgentProfile(
        agent_id="agent-sec-1",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=("web_search",),
        system_prompt="Base",
        security_overrides={"capabilities": ["web_search_tool", "net_fetch"]},
    )

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=profile)

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=chat,
        ),
        patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
    ):
        ctx = await _resolve_goal_stream_agent_context("chat-sec-1")

    assert ctx.agent_security_raw == {"capabilities": ["web_search_tool", "net_fetch"]}
