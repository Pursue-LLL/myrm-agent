"""Unit tests for ChannelAgentExecutor prompt injection logic."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import ChannelCapabilities, InboundMessage, TopicContext
from app.core.channel_bridge.agent_executor import (
    ChannelAgentExecutor,
    invalidate_agent_overrides_cache,
)
from app.services.agent.profile_resolver import get_agent_profile_resolver


@pytest.fixture
def mock_agent_factory():
    with patch("app.ai_agents.agents.AgentFactory") as factory:
        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()

        # process_stream returns an async generator
        async def mock_stream(*args, **kwargs):
            yield {"type": "message", "data": "test"}

        mock_agent.process_stream = MagicMock(side_effect=mock_stream)
        factory.create_general_agent.return_value = mock_agent
        yield factory


@pytest.fixture
def mock_load_user_configs():
    with patch("app.core.channel_bridge.agent_executor.executor.load_user_configs", new_callable=AsyncMock) as loader:
        with patch(
            "app.core.channel_bridge.agent_executor.executor.verify_search_service_available", new_callable=AsyncMock
        ) as mock_verify:
            mock_verify.return_value = True
            from myrm_agent_harness.toolkits.web_search.web_searcher import SearchServiceConfig

            from app.core.channel_bridge.config_loader import UserConfigs
            from app.core.types import ModelConfig

            mock_configs = UserConfigs(
                model_cfg=ModelConfig(provider="openai", model="test", api_key="test"),
                search_cfg=SearchServiceConfig(searchService="searxng"),
                retrieval_dict={},
                personal_settings_dict={},
                mcp_dict={},
                providers_dict={
                    "providers": [
                        {
                            "id": "openai-1",
                            "providerType": "openai",
                            "isEnabled": True,
                            "apiKeys": [{"key": "sk-test", "isActive": True}],
                        },
                    ],
                    "defaultModelConfig": {
                        "baseModel": {"primary": {"providerId": "openai-1", "model": "gpt-4o"}},
                    },
                },
                search_is_user_configured=True,
            )
            loader.return_value = mock_configs
            yield loader


@pytest.fixture
def mock_agent_service():
    with patch("app.services.agent.agent_service.AgentService") as service:
        mock_profile = MagicMock()
        mock_profile.system_prompt = "Profile system prompt."
        mock_profile.model = None
        mock_profile.model_selection = None
        mock_profile.skills = []
        mock_profile.skill_configs = None
        mock_profile.max_iterations = None
        mock_profile.memory_policy = None
        mock_profile.memory_decay_profile = None
        mock_profile.metadata = {
            "security_overrides": None,
            "personality_style": "professional",
        }
        service.get_agent_by_id = AsyncMock(return_value=mock_profile)
        yield service


@pytest.mark.asyncio
async def test_injects_prompt_when_media_false(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=ChannelCapabilities(media=False, file_upload=True, markdown=True),
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )

    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    mock_agent_factory.create_general_agent.assert_called_once()
    params = mock_agent_factory.create_general_agent.call_args[0][0]

    assert "DO NOT attempt to generate or send any images, video, or audio" in params.user_instructions
    assert "DO NOT attempt to generate or send any files or documents" not in params.user_instructions
    assert "DO NOT use Markdown formatting" not in params.user_instructions
    assert "Profile system prompt." in params.user_instructions
    assert params.memory_channel_id == "test"
    assert params.memory_conversation_id == params.chat_id
    assert isinstance(params.memory_task_id, str) and params.memory_task_id


@pytest.mark.asyncio
async def test_prefers_control_plane_resolved_identity_for_memory_scope(
    mock_agent_factory,
    mock_load_user_configs,
    mock_agent_service,
):
    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        metadata={
            "resolved_identity": {
                "platform_user_id": "owner-1",
                "sandbox_owner_id": "owner-1",
                "channel_id": "telegram",
                "channel_user_id": "tg_user_42",
                "conversation_id": "telegram:private:chat-remote",
                "task_id": "telegram:private:chat-remote",
            }
        },
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )

    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    params = mock_agent_factory.create_general_agent.call_args[0][0]
    assert params.memory_channel_id == "telegram"
    assert params.memory_conversation_id == "telegram:private:chat-remote"
    assert params.memory_task_id == "telegram:private:chat-remote"


@pytest.mark.asyncio
async def test_injects_prompt_when_all_false(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=ChannelCapabilities(media=False, file_upload=False, markdown=False),
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )

    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    mock_agent_factory.create_general_agent.assert_called_once()
    params = mock_agent_factory.create_general_agent.call_args[0][0]

    assert "DO NOT attempt to generate or send any images, video, or audio" in params.user_instructions
    assert "DO NOT attempt to generate or send any files or documents" in params.user_instructions
    assert "DO NOT use Markdown formatting" in params.user_instructions
    assert "Profile system prompt." in params.user_instructions


@pytest.mark.asyncio
async def test_does_not_inject_prompt_when_media_true(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=ChannelCapabilities(media=True, file_upload=True, markdown=True),
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )

    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    mock_agent_factory.create_general_agent.assert_called_once()
    params = mock_agent_factory.create_general_agent.call_args[0][0]

    assert "IMPORTANT: You are communicating via a channel with the following limitations" not in params.user_instructions
    assert "Profile system prompt." in params.user_instructions


@pytest.mark.asyncio
async def test_does_not_inject_prompt_when_capabilities_none(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=None,
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )

    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    mock_agent_factory.create_general_agent.assert_called_once()
    params = mock_agent_factory.create_general_agent.call_args[0][0]

    assert "IMPORTANT: You are communicating via a channel with the following limitations" not in params.user_instructions


@pytest.mark.asyncio
async def test_appends_to_existing_instructions(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    # Set existing instructions
    mock_load_user_configs.return_value.personal_settings_dict = {"systemInstructions": "Custom existing instructions."}

    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=ChannelCapabilities(media=False),
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )

    # Use topic_context to trigger agent_overrides
    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    mock_agent_factory.create_general_agent.assert_called_once()
    params = mock_agent_factory.create_general_agent.call_args[0][0]

    # Should contain custom instructions, profile prompt, and media warning
    assert params.user_instructions.startswith("Custom existing instructions.\n\nProfile system prompt.\n\nIMPORTANT:")


@pytest.mark.asyncio
async def test_handles_none_instructions(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    # No existing instructions
    mock_load_user_configs.return_value.personal_settings_dict = {}
    mock_agent_service.return_value.get_agent_by_id_and_user.return_value = None  # No profile prompt

    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=ChannelCapabilities(media=False),
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )

    stream = executor.execute_stream(
        msg=msg,
    )
    async for _ in stream:
        pass

    mock_agent_factory.create_general_agent.assert_called_once()
    params = mock_agent_factory.create_general_agent.call_args[0][0]

    assert params.user_instructions.startswith("IMPORTANT: You are communicating via a channel with the following limitations")


@pytest.mark.asyncio
async def test_channel_injects_auto_restore_domains_from_resolved_profile(
    mock_agent_factory,
    mock_load_user_configs,
):
    """Channel executor must pass ResolvedAgentProfile.auto_restore_domains into GeneralAgentParams (Web parity)."""
    from app.services.agent.profile_resolver import ResolvedAgentProfile

    resolved = ResolvedAgentProfile(
        agent_id="agent-chan-1",
        system_prompt=None,
        model=None,
        skill_ids=(),
        subagent_ids=None,
        mcp_ids=(),
        security_overrides=None,
        personality_style=None,
        max_iterations=None,
        workspace_policy=None,
        memory_policy=None,
        memory_decay_profile="normal",
        enabled_builtin_tools=("web_search", "browser"),
        auto_restore_domains=("oauth.example", "github.com"),
    )
    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=resolved)

    with patch(
        "app.core.channel_bridge.agent_executor.executor.get_agent_profile_resolver",
        return_value=mock_resolver,
    ):
        executor = ChannelAgentExecutor()
        msg = InboundMessage(
            channel="test",
            sender_id="u1",
            chat_id="c1",
            content="hi",
            sent_at=1696932000.0,
            sent_timezone="UTC",
        )
        topic_context = TopicContext(topic_id="t1", agent_id="agent-chan-1")
        stream = executor.execute_stream(msg=msg, topic_context=topic_context)
        async for _ in stream:
            pass

    mock_resolver.resolve.assert_awaited_once_with("agent-chan-1")
    params = mock_agent_factory.create_general_agent.call_args[0][0]
    assert params.auto_restore_domains == ["oauth.example", "github.com"]
    assert params.enable_browser is True
    assert params.memory_decay_profile == "normal"


@pytest.fixture(autouse=True)
def clear_agent_cache():
    """Clear agent profile resolver cache between tests."""
    resolver = get_agent_profile_resolver()
    resolver._cache.clear()
    yield
    resolver._cache.clear()


@pytest.mark.asyncio
async def test_personality_injection_from_agent_config(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    """Non-professional personality from agent config injects Communication Style suffix."""
    mock_agent_service.get_agent_by_id.return_value.metadata = {
        "security_overrides": None,
        "personality_style": "humorous",
    }

    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=ChannelCapabilities(media=True, file_upload=True, markdown=True),
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )
    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    params = mock_agent_factory.create_general_agent.call_args[0][0]
    assert "**Communication Style**:" in params.user_instructions
    assert "humorous" in params.user_instructions.lower() or "playful" in params.user_instructions.lower()


@pytest.mark.asyncio
async def test_personality_metadata_overrides_agent_config(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    """Personality from message metadata (slash command) takes priority over agent config."""
    mock_agent_service.get_agent_by_id.return_value.metadata = {
        "security_overrides": None,
        "personality_style": "academic",
    }

    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=None,
        sent_at=1696932000.0,
        sent_timezone="UTC",
        metadata={"personality_style": "concise"},
    )
    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    params = mock_agent_factory.create_general_agent.call_args[0][0]
    assert "**Communication Style**:" in params.user_instructions
    assert "concise" in params.user_instructions.lower() or "brief" in params.user_instructions.lower()
    assert "academic" not in params.user_instructions.lower()


@pytest.mark.asyncio
async def test_professional_personality_no_suffix(mock_agent_factory, mock_load_user_configs, mock_agent_service):
    """Professional personality (default) does not inject Communication Style suffix."""
    executor = ChannelAgentExecutor()
    msg = InboundMessage(
        channel="test",
        sender_id="u1",
        chat_id="c1",
        content="hi",
        channel_capabilities=ChannelCapabilities(media=True, file_upload=True, markdown=True),
        sent_at=1696932000.0,
        sent_timezone="UTC",
    )
    topic_context = TopicContext(topic_id="t1", agent_id="main")

    stream = executor.execute_stream(msg=msg, topic_context=topic_context)
    async for _ in stream:
        pass

    params = mock_agent_factory.create_general_agent.call_args[0][0]
    assert "**Communication Style**:" not in params.user_instructions


# ---------------------------------------------------------------------------
# invalidate_agent_overrides_cache tests
# ---------------------------------------------------------------------------


class TestInvalidateAgentOverridesCache:
    """Tests for the cache invalidation function (now delegates to AgentProfileResolver)."""

    def setup_method(self):
        self._resolver = get_agent_profile_resolver()
        self._resolver._cache.clear()

    def teardown_method(self):
        self._resolver._cache.clear()

    def test_removes_matching_entries(self):
        self._resolver._cache["agent-abc"] = (1.0, None)
        self._resolver._cache["agent-xyz"] = (3.0, None)

        invalidate_agent_overrides_cache("agent-abc")

        assert "agent-abc" not in self._resolver._cache
        assert "agent-xyz" in self._resolver._cache

    def test_noop_when_no_match(self):
        self._resolver._cache["agent-xyz"] = (1.0, None)

        invalidate_agent_overrides_cache("agent-nonexistent")

        assert len(self._resolver._cache) == 1

    def test_noop_on_empty_cache(self):
        invalidate_agent_overrides_cache("agent-abc")
        assert len(self._resolver._cache) == 0

    def test_does_not_remove_partial_suffix_match(self):
        self._resolver._cache["agent-abc-extended"] = (1.0, None)
        self._resolver._cache["agent-abc"] = (2.0, None)

        invalidate_agent_overrides_cache("agent-abc")

        assert "agent-abc-extended" in self._resolver._cache
        assert "agent-abc" not in self._resolver._cache
