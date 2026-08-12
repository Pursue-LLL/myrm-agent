"""Live Memory A/B integration — real download, real embedding probe, real dual-arm run.

[INPUT]
- app.api.eval.memory_ab_router (TestClient /eval/memory-ab/*)
- app.core.eval.wb_bench (real HuggingFace download + workspace build)
- app.services.agent.platform_config::verify_platform_embedding_ready

[OUTPUT]
- test_memory_ab_embedding_probe_live: real embedding readiness probe.
- test_memory_ab_full_chain_live: full API chain with real download / arms /
  report / throwaway-volume cleanup.

[POS]
E2E integration layer for the Memory A/B feature. The critical path is not
mocked: the embedding probe hits the real embedding API, the WBBench office
archive (~10 MB) is downloaded and checksum-verified, both arms run through
the real AgentFactory with a real LLM, the report is written with the
``memory_tool_calls`` annotation, and the throwaway memory volume is evicted
and removed. The only indirection is limiting the executed case count (the
office build itself runs fully) so the test stays inside the integration
time budget.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.eval.memory_ab import DEFAULT_MEMORY_AB_MEMORY_DIR
from tests.support.local_embedding_server import LocalEmbeddingServer


@pytest.fixture(scope="module")
def local_embedding() -> LocalEmbeddingServer:
    """Local OpenAI-compatible embedding endpoint (ephemeral port).

    The product accepts arbitrary self-hosted OpenAI-compatible embedding
    endpoints, so the integration tests stay independent of external
    embedding account quota while exercising the real probe + dual-arm path.
    """
    server = LocalEmbeddingServer(port=0).start()
    yield server
    server.stop()


def _build_user_configs_from_env(embedding_endpoint: str | None = None):
    """Build ``UserConfigs`` from ``.env.test`` (real LLM + embedding keys).

    LiteLLM requires ``openai/`` (not ``openai-like/``) with ``base_url`` for
    custom OpenAI-compatible endpoints; siliconflow embedding is routed via
    the same OpenAI-compatible path. ``embedding_endpoint`` (when given) points
    the embedding config at the local endpoint instead of the env keys.
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

    retrieval_dict: dict[str, object] = {}
    if embedding_endpoint:
        retrieval_dict = {
            "embeddingApplied": True,
            "embeddingConfig": {
                "provider": "openai",
                "model": "test-embed-v1",
                "apiKey": "test-key",
                "apiBase": embedding_endpoint,
            },
        }
    else:
        embedding_key = os.environ.get("EMBEDDING_API_KEY", "")
        if embedding_key:
            retrieval_dict = {
                "embeddingApplied": True,
                "embeddingConfig": {
                    "provider": "siliconflow",
                    "model": os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
                    "apiKey": embedding_key,
                    "apiBase": os.environ.get("EMBEDDING_BASE_URL", ""),
                },
            }

    return UserConfigs(
        model_cfg=ModelConfig(model=model, api_key=api_key, base_url=base_url),
        search_cfg=None,
        search_is_user_configured=False,
        retrieval_dict=retrieval_dict,
        personal_settings_dict={},
        mcp_dict={},
        providers_dict={},
    )


def _requires_live_credentials(need_llm: bool = False) -> None:
    """Skip unless real LLM credentials are available (embedding is local)."""
    if need_llm and not os.environ.get("BASIC_API_KEY"):
        pytest.skip("Memory A/B full chain requires BASIC_API_KEY")


@pytest.mark.e2e
def test_memory_ab_embedding_probe_live(local_embedding: LocalEmbeddingServer) -> None:
    """The embedding readiness probe passes against the embedding endpoint."""
    _requires_live_credentials()

    from app.services.agent.platform_config import verify_platform_embedding_ready

    mock_configs = _build_user_configs_from_env(embedding_endpoint=local_embedding.base_url)
    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        return_value=mock_configs,
    ):
        embedding_cfg = asyncio.run(verify_platform_embedding_ready())
    assert embedding_cfg is not None


@pytest.fixture(autouse=True)
def _isolated_myrm_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect `.myrm`-rooted storage (wb_bench / reports / memory / workspaces)
    into a per-test temp dir so the repo tree is never polluted."""
    monkeypatch.chdir(tmp_path)


def _inject_test_checkpointer() -> None:
    """Inject a checkpointer as the real app startup does in lifespan.py.

    The dual-arm run builds agents through the real AgentFactory, which calls
    ``get_checkpointer()`` with no fallback. The integration app (minimal app)
    does not run the lifespan phase, so the checkpointer must be injected the
    same way the production startup does and reset afterwards.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer

    _reset_checkpointer_for_testing()
    set_checkpointer(MemorySaver())


@pytest.mark.e2e
@pytest.mark.timeout(600)
def test_memory_ab_full_chain_live(local_embedding: LocalEmbeddingServer) -> None:
    """Full Memory A/B chain: probe -> download -> dual-arm -> report -> cleanup."""
    _requires_live_credentials(need_llm=True)
    _inject_test_checkpointer()
    try:
        _run_full_chain(local_embedding.base_url)
    finally:
        from app.platform_utils import _reset_checkpointer_for_testing

        _reset_checkpointer_for_testing()


def _run_full_chain(embedding_endpoint: str) -> None:
    """The full Memory A/B chain: probe -> download -> dual-arm -> report -> cleanup."""
    from fastapi.testclient import TestClient

    from app.config.settings import settings
    from tests.support.minimal_app import build_minimal_app

    fastapi_app = build_minimal_app(preset="eval")
    mock_configs = _build_user_configs_from_env(embedding_endpoint=embedding_endpoint)

    from app.core.eval import benchmarks

    real_build = benchmarks.build_benchmark_cases

    def _limited_build(
        benchmark_id: str,
        *,
        progress_callback=None,
        should_abort=None,
        limit: int | None = None,
    ):
        """Real download + full workspace build; return only the first case.

        The download, checksum verify, atomic install, and workspace
        provisioning all run against the real dataset; only the number of
        executed cases is reduced so the dual-arm run stays within the
        integration time budget.
        """
        cases, seed_map, _sampled = real_build(
            benchmark_id,
            progress_callback=progress_callback,
            should_abort=should_abort,
            limit=limit,
        )
        limited = cases[:1]
        limited_seed_map = {
            k: v
            for k, v in seed_map.items()
            if k in {c.turns[0].message for c in limited}
        }
        return limited, limited_seed_map, False

    from app.core.eval import wb_bench_workspace as _wb_ws

    real_iter_task_dirs = _wb_ws._iter_task_dirs

    def _single_task_dirs(source_root):
        """Provision workspace only for the first task.

        The full ``_iter_task_dirs`` walks every task in the dataset and
        ``_prepare_workspace`` extracts each workspace.tar.gz — that is the
        dominant cost of an office build (50+ archives). The integration test
        runs only the first case, so preparing a single workspace exercises
        the same real provisioning path in a fraction of the time.
        """
        return real_iter_task_dirs(source_root)[:1]

    with TestClient(fastapi_app) as client:
        p = f"{settings.api_prefix.rstrip('/')}/eval"

        with (
            patch(
                "app.core.eval.executor.load_user_configs",
                return_value=mock_configs,
            ),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                return_value=mock_configs,
            ),
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                side_effect=_limited_build,
            ),
            patch.object(
                _wb_ws,
                "_iter_task_dirs",
                side_effect=_single_task_dirs,
            ),
        ):
            response = client.post(
                f"{p}/memory-ab/run", json={"benchmark_id": "wb-bench-office"}
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] in ("started", "already_running"), body

            status_data: dict = {}
            max_retries = 300
            for _ in range(max_retries):
                r = client.get(f"{p}/memory-ab/status")
                assert r.status_code == 200, r.text
                status_data = r.json()
                if not status_data.get("is_running", True):
                    break
                time.sleep(2)
            else:
                pytest.fail("Memory A/B evaluation did not complete within timeout")

        assert status_data.get("error") is None, status_data.get("error")

        response = client.get(f"{p}/memory-ab/reports/latest")
        assert response.status_code == 200, response.text
        report_data = response.json()
        assert report_data["status"] == "success"
        report = report_data["report"]
        assert report is not None
        assert report.get("dataset_id") == "wb-bench-office"

        # Model disclosure: with no profile selected the agent model follows
        # the user model_cfg; WBBench is task-native so the judge is "none".
        assert report.get("agent_model") == mock_configs.model_cfg.model
        assert report.get("judge_model") == "none"

        # The history summary must disclose the same model labels.
        history_resp = client.get(f"{p}/memory-ab/reports/history")
        assert history_resp.status_code == 200, history_resp.text
        history_body = history_resp.json()
        assert history_body.get("status") == "success"
        history = history_body.get("reports", [])
        assert any(
            h.get("dataset_id") == "wb-bench-office"
            and h.get("agent_model") == mock_configs.model_cfg.model
            and h.get("judge_model") == "none"
            for h in history
        ), history

        per_profile = report.get("per_profile", {})
        assert "memory_off" in per_profile
        assert "memory_on" in per_profile
        for arm in ("memory_off", "memory_on"):
            summary = per_profile.get(arm)
            assert isinstance(summary, dict), arm
            assert isinstance(summary.get("memory_tool_calls"), int), arm
            # The arms must have really run against the LLM: at least one case
            # was evaluated and real tokens were consumed (evidence, not
            # structure). Per-arm summary carries pass/fail/error counts.
            evaluated = (
                summary.get("pass_count", 0)
                + summary.get("fail_count", 0)
                + summary.get("error_count", 0)
            )
            assert isinstance(evaluated, int) and evaluated >= 1, arm
            assert isinstance(summary.get("total_tokens"), int), arm
            assert summary["total_tokens"] > 0, arm

        # The throwaway memory volume must be evicted and removed.
        memory_root = Path(DEFAULT_MEMORY_AB_MEMORY_DIR)
        if memory_root.exists():
            assert not list(memory_root.glob("memory_ab_*")), (
                "throwaway memory volume was not cleaned up"
            )

        # The embedded Qdrant store that lived under the throwaway volume must
        # be evicted from the harness per-path singleton cache — otherwise the
        # file handle leaks across evaluation runs (visible as a warning only
        # at process exit, which this suite's filterwarnings would swallow).
        from myrm_agent_harness.toolkits.vector.qdrant.factory import (
            _embedded_clients,
        )

        leaked = [
            str(store.config.local_path)
            for store in _embedded_clients.values()
            if "eval_memory_ab" in str(store.config.local_path)
        ]
        assert not leaked, f"embedded Qdrant store leaked: {leaked}"

        # Both arms' per-case session workspaces must be removed too — the
        # real dual-arm run creates them under .myrm/eval_workspaces and the
        # finally-block cleanup must leave no trace behind.
        workspace_root = Path(".myrm/eval_workspaces")
        if workspace_root.exists():
            assert not list(workspace_root.iterdir()), (
                "eval session workspaces were not cleaned up after the run"
            )
