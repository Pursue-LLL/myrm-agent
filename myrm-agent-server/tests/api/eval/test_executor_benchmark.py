"""Unit tests for LocalEvalExecutor benchmark_mode.

Verifies that benchmark_mode=True produces a clean evaluation baseline:
- Empty system prompt (user_instructions)
- CORE-only tools (empty enabled_builtin_tools → resolve_agent_mount forces file/shell)
- No MCP, skills, subagents, shared memory
- Web search disabled
- Replan disabled via engine_params
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.eval.executor import LocalEvalExecutor


@pytest.mark.asyncio
async def test_benchmark_mode_overrides_user_config():
    """benchmark_mode=True should override all user-specific configuration."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams
    from app.core.types import ModelConfig

    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    executor = LocalEvalExecutor(profile_id="test_profile", benchmark_mode=True)
    assert executor.benchmark_mode is True

    with patch("app.core.eval.executor.AgentFactory.create_general_agent") as mock_factory:
        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield {"type": "message", "data": "benchmark response"}

        mock_agent.process_stream = mock_stream
        mock_factory.return_value = mock_agent

        with patch("app.core.eval.executor.load_user_configs") as mock_configs:
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {"server1": {"url": "http://mcp"}}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {"user_instructions": "My custom prompt"}
            mock_cfg.model_cfg = ModelConfig(provider="test", model="test-model", apiKey="key")
            mock_cfg.search_cfg = SearchServiceConfig(provider="tavily", searchService="tavily")
            mock_cfg.search_is_user_configured = True
            mock_configs.return_value = mock_cfg

            response = await executor.execute("Test task")

            assert response is not None
            assert mock_factory.called

            params = mock_factory.call_args[0][0]

            assert params.user_instructions == ""
            assert params.agent_skill_ids == []
            assert params.subagent_ids is None
            assert params.mcp_cfg is None
            assert params.enable_web_search is False
            assert params.memory_shared_context_ids == []
            assert params.engine_params == {
                "enable_replan": False,
                "enable_context_compression": False,
            }


@pytest.mark.asyncio
async def test_normal_mode_preserves_user_config():
    """benchmark_mode=False (default) should preserve user configuration."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams
    from app.core.types import ModelConfig

    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    executor = LocalEvalExecutor()
    assert executor.benchmark_mode is False

    with patch("app.core.eval.executor.AgentFactory.create_general_agent") as mock_factory:
        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield {"type": "message", "data": "normal response"}

        mock_agent.process_stream = mock_stream
        mock_factory.return_value = mock_agent

        with patch("app.core.eval.executor.load_user_configs") as mock_configs:
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {}
            mock_cfg.model_cfg = ModelConfig(provider="test", model="test-model", apiKey="key")
            mock_cfg.search_cfg = SearchServiceConfig(provider="tavily", searchService="tavily")
            mock_cfg.search_is_user_configured = False
            mock_configs.return_value = mock_cfg

            response = await executor.execute("Test task")

            assert response is not None
            params = mock_factory.call_args[0][0]

            assert params.engine_params is None


@pytest.mark.asyncio
async def test_benchmark_mode_init():
    """Verify constructor parameter handling."""
    default_exec = LocalEvalExecutor()
    assert default_exec.benchmark_mode is False
    assert default_exec.profile_id is None

    bench_exec = LocalEvalExecutor(benchmark_mode=True)
    assert bench_exec.benchmark_mode is True

    combined_exec = LocalEvalExecutor(profile_id="p1", benchmark_mode=True)
    assert combined_exec.profile_id == "p1"
    assert combined_exec.benchmark_mode is True


@pytest.mark.asyncio
async def test_resolve_shared_contexts_false_skips_injection():
    """resolve_shared_contexts=False (layered ablation) must not inject
    the user's real shared-context ids into any non-benchmark layer."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams
    from app.core.types import ModelConfig

    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    executor = LocalEvalExecutor(profile_id="p1", benchmark_mode=False, resolve_shared_contexts=False)

    with patch("app.core.eval.executor.AgentFactory.create_general_agent") as mock_factory:
        mock_agent = MagicMock()
        mock_agent.close = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield {"type": "message", "data": "ablation response"}

        mock_agent.process_stream = mock_stream
        mock_factory.return_value = mock_agent

        with (
            patch("app.core.eval.executor.load_user_configs") as mock_configs,
            patch(
                "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
                new=AsyncMock(return_value=["shared-1", "shared-2"]),
            ) as mock_resolve,
        ):
            mock_cfg = MagicMock()
            mock_cfg.retrieval_dict = {}
            mock_cfg.mcp_dict = {}
            mock_cfg.providers_dict = {}
            mock_cfg.personal_settings_dict = {}
            mock_cfg.model_cfg = ModelConfig(provider="test", model="test-model", apiKey="key")
            mock_cfg.search_cfg = SearchServiceConfig(provider="tavily", searchService="tavily")
            mock_cfg.search_is_user_configured = False
            mock_configs.return_value = mock_cfg

            await executor.execute("Test task")

            # Even though a profile is set (which would otherwise resolve
            # shared contexts), the ablation switch must skip the resolver.
            mock_resolve.assert_not_awaited()
            params = mock_factory.call_args[0][0]
            assert params.memory_shared_context_ids == []
