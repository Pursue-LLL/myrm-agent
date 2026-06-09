import os

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

    # We will run 2 concurrent cases that both write to 'test_isolation.txt'.
    # If they share a workspace, they will overwrite each other.
    # If isolated, they each get their own 'test_isolation.txt' in their respective session folder.
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

    executor = LocalEvalExecutor()
    runner = EvalRunner(executor, max_concurrency=2)

    result = await runner.run_multi_turn(cases)
    if result.fail_count > 0 or result.error_count > 0:
        for t in result.turn_results:
            print(f"Error: {t.error}")
    assert result.pass_count == 2
