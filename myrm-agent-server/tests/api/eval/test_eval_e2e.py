"""End-to-end tests for the Eval API using in-process TestClient (no external server).

TestClient runs against an in-process FastAPI app with an empty SQLite DB,
so ``load_user_configs`` has no persisted provider rows.  We patch it to
return a ``UserConfigs`` built from ``.env.test`` environment variables,
matching the real data path without requiring a pre-seeded database.
"""

import os
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

_test_root = "/tmp/myrm_test"
if not os.environ.get("MYRM_DATA_DIR"):
    os.environ["MYRM_DATA_DIR"] = _test_root
if not os.environ.get("MYRM_DLQ_DIR"):
    os.environ["MYRM_DLQ_DIR"] = f"{_test_root}/dlq"
os.environ.setdefault("METRICS_ENABLED", "true")


def _build_user_configs_from_env():
    """Build a ``UserConfigs`` from ``.env.test`` env vars (BASIC_*).

    LiteLLM requires ``openai/`` prefix (not ``openai-like/``) with a
    ``base_url`` for custom OpenAI-compatible endpoints.
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

    model_cfg = ModelConfig(
        model=model,
        api_key=api_key,
        base_url=base_url,
    )

    return UserConfigs(
        model_cfg=model_cfg,
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict={},
        personal_settings_dict={},
        mcp_dict={},
        providers_dict={},
    )


@contextmanager
def _inject_test_checkpointer():
    """Inject an in-memory checkpointer as production startup does.

    The minimal eval app does not run the lifespan phase, so the agent
    checkpointer must be injected before the run and reset afterwards.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer

    _reset_checkpointer_for_testing()
    set_checkpointer(MemorySaver())
    try:
        yield
    finally:
        _reset_checkpointer_for_testing()


@pytest.mark.e2e
def test_eval_api_e2e() -> None:
    """Exercise the full eval API lifecycle: cases -> run -> status -> reports -> metrics."""
    if not os.environ.get("BASIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("E2E test requires API key")

    if os.environ.get("BASIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["BASIC_API_KEY"]
        if os.environ.get("BASIC_BASE_URL"):
            os.environ["OPENAI_API_BASE"] = os.environ["BASIC_BASE_URL"]

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams
    from app.config.settings import settings
    from tests.support.minimal_app import build_minimal_app

    fastapi_app = build_minimal_app(preset="eval")
    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    cases_content = '{"message": "Reply with a single short sentence only.", "expected_tools": []}\n'

    mock_configs = _build_user_configs_from_env()

    with _inject_test_checkpointer():
        with TestClient(fastapi_app) as client:
            p = f"{settings.api_prefix.rstrip('/')}/eval"

            response = client.put(f"{p}/cases", json={"content": cases_content})
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "success"

            response = client.get(f"{p}/cases")
            assert response.status_code == 200
            assert response.json()["status"] == "success"
            assert response.json()["content"] == cases_content

            # Test capture from chat into evaluation dataset
            from app.services.chat.chat_service import ChatService
            class MockMsg:
                def __init__(self, role, content, extra_data=None):
                    self.role = role
                    self.content = content
                    self.extra_data = extra_data

            fake_msgs = [
                MockMsg("user", "Summarize quarterly report."),
                MockMsg("assistant", "Quarterly profit up 20%."),
            ]
            with patch.object(ChatService, "get_all_messages", new_callable=AsyncMock) as mock_msgs:
                mock_msgs.return_value = fake_msgs
                cap_res = client.post(f"{p}/cases/from-chat/chat-e2e-live?dataset_id=live-e2e-pack")
                assert cap_res.status_code == 200
                assert cap_res.json()["status"] == "success"

                pack_res = client.get(f"{p}/datasets/live-e2e-pack")
                assert pack_res.status_code == 200
                assert "Summarize quarterly report." in pack_res.json()["content"]
                assert "Quarterly profit up 20%." in pack_res.json()["content"]

            workspace_root = Path(".myrm/eval_workspaces")
            before_workspaces = set(workspace_root.iterdir()) if workspace_root.exists() else set()
            with (
                patch(
                    "app.core.eval.executor.load_user_configs",
                    return_value=mock_configs,
                ),
                patch(
                    "app.core.channel_bridge.config_loader.load_user_configs",
                    return_value=mock_configs,
                ),
            ):
                response = client.post(f"{p}/run")
                assert response.status_code == 200
                assert response.json()["status"] in ("started", "already_running")

                max_retries = 60
                status_data: dict = {}
                for _ in range(max_retries):
                    r = client.get(f"{p}/status")
                    assert r.status_code == 200, r.text
                    status_data = r.json()
                    if not status_data.get("is_running", True):
                        break
                    time.sleep(2)
                else:
                    pytest.fail("Evaluation did not complete within timeout")

            assert status_data.get("error") is None
            assert status_data.get("total") == 1
            assert status_data.get("completed") == 1

            response = client.get(f"{p}/reports/latest")
            assert response.status_code == 200
            report_data = response.json()
            assert report_data["status"] == "success"
            summary = report_data["summary"]
            assert summary is not None
            assert summary.get("total_cases") == 1
            assert summary.get("pass_count", 0) >= 0

            # Manifest model disclosure: no profile selected, so the agent model
            # falls back to model_cfg (LiteLLM-normalized) and the judge reuses
            # the same credentials.
            manifest = summary.get("manifest") or {}
            expected_provider, _, expected_model_id = mock_configs.model_cfg.model.partition("/")
            assert manifest.get("judge_model") == mock_configs.model_cfg.model
            assert manifest.get("model_provider") == expected_provider
            assert manifest.get("model_id") == expected_model_id

            response = client.get(f"{p}/internal/metrics/eval")
            assert response.status_code == 200
            metrics_data = response.json()
            assert metrics_data["status"] == "success"
            assert metrics_data.get("metrics", {}).get("total_cases") == 1

            # The eval run's per-case session workspaces must be removed once the
            # suite finishes (the finally-block cleanup runs on success too).
            # The before_workspaces snapshot is taken before POST /run, so a run
            # that leaves no new workspaces behind passes even when a sibling
            # test's stale workspaces are present in the same shared directory.
            assert not (set(workspace_root.iterdir()) - before_workspaces), (
                "eval session workspaces were not cleaned up after the run"
            )

            prom = client.get("/metrics", follow_redirects=True)
            if prom.status_code == 200:
                assert "python_gc_objects_collected_total" in prom.text
            else:
                assert prom.status_code == 404
