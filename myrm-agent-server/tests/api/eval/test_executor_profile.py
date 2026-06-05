from unittest.mock import MagicMock, patch

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

    with patch("app.core.eval.executor.AgentFactory.create_general_agent") as mock_agent_factory:
        # Mock the async generator for the agent's ainvoke
        async def mock_ainvoke(*args, **kwargs):
            yield {"agent": {"messages": [{"content": "Hello eval"}]}}

        mock_agent = MagicMock()
        from unittest.mock import AsyncMock

        mock_agent.close = AsyncMock()
        mock_agent.process_stream = mock_ainvoke
        mock_agent_factory.return_value = mock_agent

        with patch("app.core.eval.executor.load_user_configs") as mock_configs:
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {}
            mock_cfg.model_cfg = ModelConfig(provider="test", model="test", apiKey="test")
            mock_cfg.search_cfg = SearchServiceConfig(provider="tavily", searchService="tavily")
            mock_configs.return_value = mock_cfg

            with patch("app.services.agent.profile_resolver.get_agent_profile_resolver") as mock_resolver_getter:
                mock_resolver_getter.return_value = MockProfileResolver(MockResolvedProfile())

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
                assert params.agent_security_raw == {"yolo_mode_enabled": True, "test_override": True}
                assert params.max_iterations == 5
                assert params.memory_policy is not None
