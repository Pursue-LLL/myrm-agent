from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.eval.executor import LocalEvalExecutor


class MockProfileResolver:
    def __init__(self, profile):
        self.profile = profile

    async def resolve(self, profile_id):
        if profile_id == "mock_id":
            return self.profile
        return None


class MockResolvedProfile:
    def __init__(self):
        from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy

        self.system_prompt = "Custom system prompt"
        self.skill_ids = ["skill1", "skill2"]
        self.subagent_ids = ["sub1"]
        self.security_overrides = {"test_override": True}
        self.max_iterations = 5
        self.memory_policy = AgentMemoryPolicy()
        self.engine_params = None
        self.model = None
        self.enabled_builtin_tools = ("web_search",)
        self.auto_restore_domains = ()
        self.memory_decay_profile = None
        self.memory_extraction_preset = None
        self.mcp_ids: list[str] | None = None
        self.mcp_tool_selections: dict[str, list[str]] | None = None
        self.personality_style = None


@pytest.mark.asyncio
async def test_server_eval_executor_profile(tmp_path):
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams
    from app.core.types import ModelConfig

    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    # Test executor initialization with profile_id
    executor = LocalEvalExecutor(profile_id="mock_id")
    assert executor.profile_id == "mock_id"

    with patch(
        "app.core.eval.executor.AgentFactory.create_general_agent"
    ) as mock_agent_factory:
        # Mock the async generator for the agent's ainvoke
        async def mock_ainvoke(*args, **kwargs):
            yield {"agent": {"messages": [{"content": "Hello eval"}]}}

        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()
        mock_agent.process_stream = mock_ainvoke
        mock_agent_factory.return_value = mock_agent

        with patch("app.core.eval.executor.load_user_configs") as mock_configs:
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {}
            mock_cfg.model_cfg = ModelConfig(
                provider="test", model="test", apiKey="test"
            )
            mock_cfg.search_cfg = SearchServiceConfig(
                provider="tavily", searchService="tavily"
            )
            mock_configs.return_value = mock_cfg

            with patch(
                "app.services.agent.profile_resolver.get_agent_profile_resolver"
            ) as mock_resolver_getter:
                mock_resolver_getter.return_value = MockProfileResolver(
                    MockResolvedProfile()
                )

                # Execute with a fake message
                response = await executor.execute("Hello")

                # Assert that the profile settings were parsed
                assert response is not None
                assert mock_agent_factory.called

                # Verify params passed to create_general_agent
                params = mock_agent_factory.call_args[0][0]
                assert params.agent_id == "mock_id"
                assert "Custom system prompt" in params.user_instructions
                assert params.agent_skill_ids == ["skill1", "skill2"]
                assert params.subagent_ids == ["sub1"]
                assert params.agent_security_raw == {
                    "yolo_mode_enabled": True,
                    "test_override": True,
                }
                assert params.max_iterations == 5
                assert params.memory_policy is not None


class TestExecutorSessionAndWorkspace:
    """Session creation, sandbox executor lookup, and workspace seeding."""

    @pytest.mark.asyncio
    async def test_create_session_and_get_sandbox_executor(self) -> None:
        executor = LocalEvalExecutor()
        session_id = await executor.create_session()
        assert session_id.startswith("eval_")
        assert executor._session_id == session_id

        sandbox = executor.get_sandbox_executor()
        assert sandbox is not None
        # Explicit session ID hit
        assert executor.get_sandbox_executor(session_id) is sandbox
        # Unknown session falls back to the active session executor
        assert executor.get_sandbox_executor("unknown") is sandbox

    def test_get_sandbox_executor_without_session(self) -> None:
        executor = LocalEvalExecutor()
        assert executor.get_sandbox_executor() is None

    @pytest.mark.asyncio
    async def test_workspace_seeding_copies_seed_dir(self, tmp_path) -> None:
        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            EmbeddingConfig,
        )
        from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
        from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

        import app.ai_agents.agents as agent_types_mod
        from app.ai_agents.agents import GeneralAgentParams
        from app.core.types import ModelConfig

        agent_types_mod.EmbeddingConfig = EmbeddingConfig
        agent_types_mod.RerankerConfig = RerankerConfig
        GeneralAgentParams.model_rebuild()

        seed_dir = tmp_path / "seed"
        seed_dir.mkdir()
        (seed_dir / "task.md").write_text("asset")

        executor = LocalEvalExecutor(workspace_seed_map={"Hello": str(seed_dir)})

        async def mock_ainvoke(*args, **kwargs):
            yield {"type": "message", "data": "Hello"}

        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()
        mock_agent.process_stream = mock_ainvoke
        with (
            patch(
                "app.core.eval.executor.AgentFactory.create_general_agent",
                return_value=mock_agent,
            ),
            patch("app.core.eval.executor.load_user_configs") as mock_configs,
            patch("app.core.eval.executor.shutil.copytree") as mock_copytree,
        ):
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {}
            mock_cfg.model_cfg = ModelConfig(
                provider="test", model="test", apiKey="test"
            )
            mock_cfg.search_cfg = SearchServiceConfig(
                provider="tavily", searchService="tavily"
            )
            mock_configs.return_value = mock_cfg
            with patch(
                "app.services.agent.resolve_enable_web_fetch.resolve_enable_web_fetch",
                return_value=False,
            ):
                await executor.execute("Hello")

        mock_copytree.assert_called_once()

    @pytest.mark.asyncio
    async def test_workspace_seed_missing_warns(self, tmp_path) -> None:
        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            EmbeddingConfig,
        )
        from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
        from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

        import app.ai_agents.agents as agent_types_mod
        from app.ai_agents.agents import GeneralAgentParams
        from app.core.types import ModelConfig

        agent_types_mod.EmbeddingConfig = EmbeddingConfig
        agent_types_mod.RerankerConfig = RerankerConfig
        GeneralAgentParams.model_rebuild()

        executor = LocalEvalExecutor(
            workspace_seed_map={"Hello": str(tmp_path / "nope")}
        )

        async def mock_ainvoke(*args, **kwargs):
            yield {"type": "message", "data": "Hello"}

        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()
        mock_agent.process_stream = mock_ainvoke
        with (
            patch(
                "app.core.eval.executor.AgentFactory.create_general_agent",
                return_value=mock_agent,
            ),
            patch("app.core.eval.executor.load_user_configs") as mock_configs,
            patch("app.core.eval.executor.logger.warning") as mock_warn,
        ):
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {}
            mock_cfg.model_cfg = ModelConfig(
                provider="test", model="test", apiKey="test"
            )
            mock_cfg.search_cfg = SearchServiceConfig(
                provider="tavily", searchService="tavily"
            )
            mock_configs.return_value = mock_cfg
            with patch(
                "app.services.agent.resolve_enable_web_fetch.resolve_enable_web_fetch",
                return_value=False,
            ):
                await executor.execute("Hello")

        mock_warn.assert_called_once()


class TestExecutorEventParsing:
    """Verify event-type parsing collects text, tool names, and token usage."""

    @pytest.mark.asyncio
    async def test_collects_all_event_types(self) -> None:
        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            EmbeddingConfig,
        )
        from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
        from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

        import app.ai_agents.agents as agent_types_mod
        from app.ai_agents.agents import GeneralAgentParams
        from app.core.types import ModelConfig

        agent_types_mod.EmbeddingConfig = EmbeddingConfig
        agent_types_mod.RerankerConfig = RerankerConfig
        GeneralAgentParams.model_rebuild()

        executor = LocalEvalExecutor(benchmark_mode=True)

        async def mock_ainvoke(*args, **kwargs):
            yield {"type": "message", "data": "first"}
            yield {"type": "tasks_steps", "tool_name": "memory_search_tool"}
            yield {"type": "tasks_steps", "step_key": "fallback_tool"}
            yield {"type": "tasks_steps"}
            yield {
                "type": "token_usage",
                "data": {"input_tokens": 10, "output_tokens": 5},
            }
            yield {"type": "token_usage", "data": "not-a-dict"}
            yield {"type": "message", "data": "second"}

        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()
        mock_agent.process_stream = mock_ainvoke
        with (
            patch(
                "app.core.eval.executor.AgentFactory.create_general_agent",
                return_value=mock_agent,
            ),
            patch("app.core.eval.executor.load_user_configs") as mock_configs,
        ):
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {}
            mock_cfg.model_cfg = ModelConfig(
                provider="test", model="test", apiKey="test"
            )
            mock_cfg.search_cfg = SearchServiceConfig(
                provider="tavily", searchService="tavily"
            )
            mock_configs.return_value = mock_cfg
            with patch(
                "app.services.agent.resolve_enable_web_fetch.resolve_enable_web_fetch",
                return_value=False,
            ):
                response = await executor.execute("Hello")

        assert response.answer == "firstsecond"
        assert response.tools_called == ["memory_search_tool", "fallback_tool"]
        assert response.token_usage == {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
        }
        assert "execution_ms" in response.extra_timings
