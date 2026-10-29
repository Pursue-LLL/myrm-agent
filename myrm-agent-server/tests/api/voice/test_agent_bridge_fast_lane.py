"""Voice agent bridge: agent params assembly and the fast lane with its supervisor.

Covers:
  - VoiceAgentBridge._build_agent_params: web fetch gate
  - VoiceAgentBridge fast lane: query classification, no working hint, supervisor handoff on timeout, fallback
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.support.voice_bridge import make_bridge


class TestBuildAgentParamsWebFetchGate:
    """Voice bridge must honor Agent Security net_fetch like Web/Channel."""

    @pytest.mark.asyncio
    async def test_enable_web_fetch_false_when_profile_omits_net_fetch(self) -> None:
        from app.core.types import ModelConfig
        from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

        bridge = make_bridge()
        profile = ResolvedAgentProfile(
            agent_id="restricted-agent",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("file_read",),
            security_overrides={"capabilities": ["file_read"]},
        )
        mock_configs = MagicMock()
        mock_configs.model_cfg = ModelConfig(model="test/model", api_key="test-key")
        mock_configs.providers_dict = {}
        mock_configs.retrieval_dict = {}
        mock_configs.mcp_dict = {}
        mock_configs.search_cfg = None
        mock_configs.personal_settings_dict = {}

        with (
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            ) as mock_get_resolver,
            patch(
                "app.core.channel_bridge.config_parsers.verify_search_service_available",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_fallback_model_configs",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_lite_model_config",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_retrieval_models",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_mcp_configs",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_user_instructions",
                return_value="",
            ),
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=profile)
            mock_get_resolver.return_value = mock_resolver

            params = await bridge._build_agent_params("read https://example.com")

        assert params is not None
        assert params.enable_web_fetch is False
        assert params.agent_security_raw == {"capabilities": ["file_read"]}

    @pytest.mark.asyncio
    async def test_enable_web_fetch_true_when_no_security_overrides(self) -> None:
        from app.core.types import ModelConfig
        from app.services.agent.profile.profile_resolver import ResolvedAgentProfile

        bridge = make_bridge()
        profile = ResolvedAgentProfile(
            agent_id="default-agent",
            skill_ids=(),
            mcp_ids=(),
            enabled_builtin_tools=("file_read", "web_search"),
        )
        mock_configs = MagicMock()
        mock_configs.model_cfg = ModelConfig(model="test/model", api_key="test-key")
        mock_configs.providers_dict = {}
        mock_configs.retrieval_dict = {}
        mock_configs.mcp_dict = {}
        mock_configs.search_cfg = None
        mock_configs.personal_settings_dict = {}

        with (
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
            patch(
                "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            ) as mock_get_resolver,
            patch(
                "app.core.channel_bridge.config_parsers.verify_search_service_available",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_fallback_model_configs",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_lite_model_config",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_retrieval_models",
                return_value=(None, None),
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_mcp_configs",
                return_value=None,
            ),
            patch(
                "app.core.channel_bridge.config_parsers.extract_user_instructions",
                return_value="",
            ),
        ):
            mock_resolver = MagicMock()
            mock_resolver.resolve = AsyncMock(return_value=profile)
            mock_get_resolver.return_value = mock_resolver

            params = await bridge._build_agent_params("hello")

        assert params is not None
        assert params.enable_web_fetch is True
        assert params.agent_security_raw is None


class TestVoiceFastLaneAndSupervisor:
    """Tests for Voice Fast Lane quick response and 15s supervisor handoff."""

    def test_is_fast_lane_query_simple_greeting(self) -> None:
        bridge = make_bridge()
        mock_params = MagicMock()
        mock_params.agent_skill_ids = []
        mock_params.subagent_ids = None

        assert bridge._is_fast_lane_query("你好", mock_params) is True
        assert bridge._is_fast_lane_query("hello", mock_params) is True
        assert bridge._is_fast_lane_query("thanks", mock_params) is True

    def test_is_fast_lane_query_complex_rejected(self) -> None:
        bridge = make_bridge()
        mock_params = MagicMock()
        mock_params.agent_skill_ids = []
        mock_params.subagent_ids = None

        # Complex query with coding/reasoning/tools
        assert bridge._is_fast_lane_query("帮我重构一下这段代码并执行测试", mock_params) is False
        assert bridge._is_fast_lane_query("prove the pythagorean theorem step by step", mock_params) is False

    def test_is_fast_lane_query_skills_rejected(self) -> None:
        bridge = make_bridge()
        mock_params = MagicMock()
        mock_params.agent_skill_ids = ["skill-1"]
        mock_params.subagent_ids = None

        # Even simple greetings with active skills bypass fast lane
        assert bridge._is_fast_lane_query("你好", mock_params) is False

    @pytest.mark.asyncio
    async def test_fast_lane_execution_skips_working_hint(self) -> None:
        bridge = make_bridge()
        mock_params = MagicMock()
        mock_params.agent_skill_ids = []
        mock_params.subagent_ids = None

        async def fake_fast_stream(params: object, cancel_token: object) -> AsyncIterator[dict[str, object]]:
            yield {"type": "message", "data": "你好！有什么我可以帮你的？"}

        with (
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_is_fast_lane_query", return_value=True),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock) as mock_hint,
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock) as mock_stream_tts,
            patch(
                "app.services.agent.stream_session.stream_lane_factory.create_fast_lane_stream",
                side_effect=fake_fast_stream,
            ),
        ):
            await bridge.handle_stt_final("你好")

        # Working hint must NOT be called for fast lane!
        mock_hint.assert_not_called()
        mock_stream_tts.assert_called()
        assert len(bridge._transcript) == 2
        assert bridge._transcript[0].text == "你好"
        assert bridge._transcript[1].text == "你好！有什么我可以帮你的？"

    @pytest.mark.asyncio
    async def test_supervisor_handoff_on_timeout(self) -> None:
        bridge = make_bridge()
        mock_params = MagicMock()
        mock_params.agent_skill_ids = []
        mock_params.subagent_ids = None

        async def fake_slow_stream(*args: object, **kwargs: object) -> tuple[str, bool]:
            await asyncio.sleep(2.0)  # simulate slow execution
            return "done", False

        mock_handler = AsyncMock()
        mock_handler.spawn_background = AsyncMock(return_value="task-12345")

        with (
            patch("app.api.voice.agent_bridge._VOICE_SUPERVISOR_TIMEOUT_S", 0.05),
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_is_fast_lane_query", return_value=False),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock),
            patch.object(bridge, "_consume_agent_stream", side_effect=fake_slow_stream),
            patch.object(bridge, "_stream_tts_segment", new_callable=AsyncMock) as mock_stream_tts,
            patch(
                "app.core.channel_bridge.setup.get_background_task_handler",
                return_value=mock_handler,
            ),
        ):
            await bridge.handle_stt_final("帮我做一个长耗时分析")

        mock_handler.spawn_background.assert_awaited_once()
        mock_stream_tts.assert_called()

    @pytest.mark.asyncio
    async def test_fast_lane_fallback_self_healing(self) -> None:
        """If fast lane stream fails without output, fallback to full agent stream."""
        bridge = make_bridge()
        mock_params = MagicMock()
        mock_params.agent_skill_ids = []
        mock_params.subagent_ids = None

        async def failing_fast_stream(params: object, cancel_token: object) -> AsyncIterator[dict[str, object]]:
            raise RuntimeError("Fast lane provider boom")
            yield {}  # make it a generator

        with (
            patch.object(bridge, "_build_agent_params", return_value=mock_params),
            patch.object(bridge, "_is_fast_lane_query", return_value=True),
            patch.object(bridge, "_tts_working_hint", new_callable=AsyncMock),
            patch.object(
                bridge, "_consume_agent_stream", new_callable=AsyncMock, return_value=("Recovered full text.", False)
            ) as mock_full_stream,
            patch(
                "app.services.agent.stream_session.stream_lane_factory.create_fast_lane_stream",
                side_effect=failing_fast_stream,
            ),
        ):
            await bridge.handle_stt_final("hello")

        mock_full_stream.assert_awaited_once()
        assert len(bridge._transcript) == 2
        assert bridge._transcript[1].text == "Recovered full text."
