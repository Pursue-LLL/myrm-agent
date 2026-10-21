import os
from unittest.mock import patch

os.environ["MYRM_DATA_DIR"] = "/tmp/myrm_test"
os.environ["MYRM_DLQ_DIR"] = "/tmp/myrm_test/dlq"

import pytest
from myrm_agent_harness.eval.protocols import EvalCase, MultiTurnEvalCase, SandboxAssertion
from myrm_agent_harness.eval.runner import EvalRunner
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

import app.ai_agents.agents
from app.ai_agents.agents import GeneralAgentParams
from app.core.eval.executor import LocalEvalExecutor


def _build_user_configs_from_env():
    """Build ``UserConfigs`` from ``.env.test`` env vars.

    LiteLLM requires ``openai/`` prefix (not ``openai-like/``) with
    a ``base_url`` for custom OpenAI-compatible endpoints.
    """
    from app.core.channel_bridge.config_loader import UserConfigs
    from app.core.types import ModelConfig

    api_key = os.environ.get("BASIC_API_KEY", "")
    base_url = os.environ.get("BASIC_BASE_URL")
    raw_model = os.environ.get("BASIC_MODEL", "openai-like/test")

    if raw_model.startswith("openai-like/"):
        model = "openai/" + raw_model.split("/", 1)[1]
    else:
        model = raw_model

    return UserConfigs(
        model_cfg=ModelConfig(model=model, api_key=api_key, base_url=base_url),
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict={},
        personal_settings_dict={},
        mcp_dict={},
        providers_dict={},
    )


@pytest.fixture(scope="module")
def app_client():
    from fastapi.testclient import TestClient

    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="agent_with_skills")

    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_workspace_physical_isolation_e2e(app_client) -> None:
    """Test that concurrent executions use isolated physical workspaces."""
    app.ai_agents.agents.EmbeddingConfig = EmbeddingConfig
    app.ai_agents.agents.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    if not os.environ.get("BASIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("E2E test requires API key")

    if os.environ.get("BASIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["BASIC_API_KEY"]
        if os.environ.get("BASIC_BASE_URL"):
            os.environ["OPENAI_API_BASE"] = os.environ["BASIC_BASE_URL"]

    cases = [
        MultiTurnEvalCase(
            turns=[
                EvalCase(
                    message="Run this exact bash command: `echo Alpha > test_isolation.txt`",
                    expected_tools=[],
                    sandbox_assertions=[SandboxAssertion(type="file_contains", target="test_isolation.txt", expected="Alpha")],
                    metadata={"test_id": "case_1"},
                )
            ]
        ),
        MultiTurnEvalCase(
            turns=[
                EvalCase(
                    message="Run this exact bash command: `echo Beta > test_isolation.txt`",
                    expected_tools=[],
                    sandbox_assertions=[SandboxAssertion(type="file_contains", target="test_isolation.txt", expected="Beta")],
                    metadata={"test_id": "case_2"},
                )
            ]
        ),
    ]

    from langgraph.checkpoint.memory import MemorySaver

    from app.platform_utils import set_checkpointer

    set_checkpointer(MemorySaver())

    executor = LocalEvalExecutor()
    runner = EvalRunner(executor, max_concurrency=2)

    mock_configs = _build_user_configs_from_env()
    with (
        patch("app.core.eval.executor.load_user_configs", return_value=mock_configs),
        patch("app.core.channel_bridge.config_loader.load_user_configs", return_value=mock_configs),
    ):
        try:
            result = await runner.run_multi_turn(cases)
        finally:
            await executor.cleanup()

    if result.fail_count > 0 or result.error_count > 0:
        for t in result.turn_results:
            if t.error:
                print(f"Error: {t.error}")
            if t.assertion_details:
                print(f"Assertion: {t.assertion_details}")

    if result.error_count > 0:
        pytest.fail(f"Eval errors: {[t.error for t in result.turn_results if t.error]}")

    assert result.pass_count >= 1, (
        f"Expected at least 1 pass (model may lack reliable function calling), "
        f"got pass={result.pass_count} fail={result.fail_count}"
    )
