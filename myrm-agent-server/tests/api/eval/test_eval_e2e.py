"""End-to-end tests for the Eval API using in-process TestClient (no external server).

TestClient runs against an in-process FastAPI app with an empty SQLite DB,
so ``load_user_configs`` has no persisted provider rows.  We patch it to
return a ``UserConfigs`` built from ``.env.test`` environment variables,
matching the real data path without requiring a pre-seeded database.
"""

import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_test_root = "/tmp/myrm_test"
if not os.environ.get("MYRM_DATA_DIR"):
    os.environ["MYRM_DATA_DIR"] = _test_root
if not os.environ.get("MYRM_DLQ_DIR"):
    os.environ["MYRM_DLQ_DIR"] = f"{_test_root}/dlq"
os.environ.setdefault("METRICS_ENABLED", "true")


def _build_user_configs_from_env():
    """Build a ``UserConfigs`` from ``.env.test`` env vars (BASIC_*)."""
    from app.core.channel_bridge.config_loader import UserConfigs
    from app.core.types import ModelConfig

    api_key = os.environ.get("BASIC_API_KEY", "")
    base_url = os.environ.get("BASIC_BASE_URL")
    model = os.environ.get("BASIC_MODEL", "openai-like/test")

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

    with TestClient(fastapi_app) as client:
        p = f"{settings.api_prefix.rstrip('/')}/eval"

        response = client.put(f"{p}/cases", json={"content": cases_content})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "success"

        response = client.get(f"{p}/cases")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["content"] == cases_content

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

        response = client.get(f"{p}/internal/metrics/eval")
        assert response.status_code == 200
        metrics_data = response.json()
        assert metrics_data["status"] == "success"
        assert metrics_data.get("metrics", {}).get("total_cases") == 1

        prom = client.get("/metrics", follow_redirects=True)
        if prom.status_code == 200:
            assert "python_gc_objects_collected_total" in prom.text
        else:
            assert prom.status_code == 404
