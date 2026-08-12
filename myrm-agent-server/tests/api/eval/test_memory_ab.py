"""Tests for Memory A/B evaluation: executor params, service flow, router endpoints."""

import json
from collections.abc import Generator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.eval import browse_comp  # noqa: F401  (module-level benchmark registration)
from app.core.eval.executor import LocalEvalExecutor
from tests.support.minimal_app import build_minimal_app


class TestLocalEvalExecutorMemoryParams:
    """Verify enable_memory/memory_base_path are forwarded to GeneralAgentParams."""

    def _executor(self, **kwargs) -> LocalEvalExecutor:
        return LocalEvalExecutor(**kwargs)

    def test_benchmark_mode_defaults_to_no_memory(self) -> None:
        executor = self._executor(benchmark_mode=True)
        assert executor._enable_memory is False

    def test_interactive_defaults_to_memory_on(self) -> None:
        executor = self._executor()
        assert executor._enable_memory is True

    def test_explicit_enable_memory_overrides_benchmark(self) -> None:
        executor = self._executor(benchmark_mode=True, enable_memory=True)
        assert executor._enable_memory is True

    def test_memory_base_path_forwarded(self) -> None:
        executor = self._executor(memory_base_path="/tmp/isolated_memory")
        assert executor._memory_base_path == "/tmp/isolated_memory"


@pytest.mark.asyncio
async def test_executor_passes_enable_memory_and_base_path_to_params():
    """Full execute() path forwards the flags into GeneralAgentParams."""
    from unittest.mock import AsyncMock

    from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig
    from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig
    from myrm_agent_harness.toolkits.web_search import SearchServiceConfig

    import app.ai_agents.agents as agent_types_mod
    from app.ai_agents.agents import GeneralAgentParams
    from app.core.types import ModelConfig

    agent_types_mod.EmbeddingConfig = EmbeddingConfig
    agent_types_mod.RerankerConfig = RerankerConfig
    GeneralAgentParams.model_rebuild()

    executor = LocalEvalExecutor(
        benchmark_mode=True,
        enable_memory=True,
        memory_base_path="/tmp/isolated_memory_ab",
    )

    async def mock_ainvoke(*args, **kwargs):
        yield {"type": "message", "data": "Hello"}

    mock_agent = MagicMock()
    mock_agent.close = AsyncMock()
    mock_agent.process_stream = mock_ainvoke
    with (
        patch(
            "app.core.eval.executor.AgentFactory.create_general_agent"
        ) as mock_factory,
        patch("app.core.eval.executor.load_user_configs") as mock_configs,
    ):
        mock_factory.return_value = mock_agent
        mock_cfg = MagicMock()
        mock_cfg.retrieval_dict = {}
        mock_cfg.mcp_dict = {}
        mock_cfg.providers_dict = {}
        mock_cfg.personal_settings_dict = {}
        mock_cfg.model_cfg = ModelConfig(provider="test", model="test", apiKey="test")
        mock_cfg.search_cfg = SearchServiceConfig(
            provider="tavily", searchService="tavily"
        )
        mock_configs.return_value = mock_cfg

        with patch(
            "app.services.agent.resolve_enable_web_fetch.resolve_enable_web_fetch",
            return_value=False,
        ):
            response = await executor.execute("Hello")

    assert response is not None
    params = mock_factory.call_args[0][0]
    assert params.enable_memory is True
    assert params.memory_base_path == "/tmp/isolated_memory_ab"
    assert params.engine_params == {
        "enable_replan": False,
        "enable_context_compression": False,
    }


class TestMemoryAbService:
    """Verify the service orchestrates two arms via MatrixRunner and cleans up."""

    @pytest.mark.asyncio
    async def test_run_memory_ab_flow(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        class FakeMatrixResult:
            per_profile_results: dict[str, object] = {
                "memory_off": MagicMock(
                    turn_results=[
                        MagicMock(
                            response=MagicMock(
                                tools_called=["web_search_tool", "open_url_tool"]
                            )
                        )
                    ]
                ),
                "memory_on": MagicMock(
                    turn_results=[
                        MagicMock(
                            response=MagicMock(
                                tools_called=[
                                    "memory_search_tool",
                                    {"name": "memory_save_tool"},
                                ]
                            )
                        )
                    ]
                ),
            }

            def to_dict(self) -> dict[str, object]:
                return {
                    "profile_ids": ["memory_off", "memory_on"],
                    "total_cases": 1,
                    "per_profile": {
                        "memory_off": {"pass_count": 1, "pass_rate": 1.0},
                        "memory_on": {"pass_count": 1, "pass_rate": 1.0},
                    },
                }

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.executors = executors
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, cases, **kwargs):
                self.kwargs["on_profile_start"]("memory_off", 0, 2)
                self.kwargs["on_profile_start"]("memory_on", 1, 2)
                self.kwargs["on_case_complete"]("memory_off", MagicMock())
                self.kwargs["on_case_complete"]("memory_on", MagicMock())
                return FakeMatrixResult()

        cases = [MagicMock()]
        cases[0].turns = [MagicMock()]

        evict_mock = AsyncMock()
        reports_dir = tmp_path / "memory_ab_reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text('{"stale": true}')
        memory_dir = tmp_path / "eval_memory_ab"

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = memory_dir

        def fake_build(
            benchmark_id: str,
            *,
            limit: int | None = None,
            progress_callback: object = None,
            should_abort: object = None,
        ) -> tuple[list[object], dict[str, str], bool]:
            assert progress_callback is not None
            assert should_abort is not None
            progress_callback(10, 20)
            assert should_abort() is False
            return (cases, {}, True)

        with (
            patch(
                "app.core.eval.memory_ab._memory_ab_state",
                {"is_running": False, "abort_requested": False},
            ),
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                side_effect=fake_build,
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(return_value="deepseek/deepseek-chat"),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager", evict_mock
            ),
        ):
            await memory_ab_mod.run_memory_ab_background(
                "wb-bench-code", profile_id="agent_x", limit=1
            )
            # Progress callbacks drive the live SSE state.
            assert memory_ab_mod._memory_ab_state["current_arm"] == "memory_on"
            assert memory_ab_mod._memory_ab_state["case_completed"] == 2
            assert memory_ab_mod._memory_ab_state["download_progress"] == {
                "downloaded_bytes": 10,
                "total_bytes": 20,
            }

        latest = reports_dir / "latest.json"
        assert latest.exists()
        report = latest.read_text()
        assert '"memory_off"' in report
        assert '"memory_on"' in report
        assert '"limit": 1' in report
        assert '"judge_model": "none"' in report
        assert '"agent_model": "deepseek/deepseek-chat"' in report
        assert '"memory_tool_calls"' in report
        assert '"stale"' not in report
        evict_mock.assert_awaited_once()
        assert not memory_dir.exists()

    @pytest.mark.asyncio
    async def test_run_memory_ab_discloses_judge_and_agent_model(
        self, tmp_path: Path
    ) -> None:
        """LLM-judged benchmarks record the resolved judge and agent model."""
        import app.core.eval.memory_ab as memory_ab_mod

        class FakeMatrixResult:
            per_profile_results: dict[str, object] = {}

            def to_dict(self) -> dict[str, object]:
                return {"profile_ids": ["memory_off", "memory_on"], "total_cases": 1}

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.executors = executors
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, cases, **kwargs):
                return FakeMatrixResult()

        cases = [MagicMock()]
        cases[0].turns = [MagicMock()]

        reports_dir = tmp_path / "reports"
        memory_dir = tmp_path / "memory"
        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = memory_dir

        with (
            patch(
                "app.core.eval.memory_ab._memory_ab_state",
                {"is_running": False, "abort_requested": False},
            ),
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=(cases, {}, False),
            ),
            patch(
                "app.core.eval.model_config._resolve_judge_config",
                new=AsyncMock(return_value=("judge-cfg", "deepseek/deepseek-chat")),
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(return_value="gpt-4o"),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager", AsyncMock()
            ),
        ):
            await memory_ab_mod.run_memory_ab_background(
                "browsecomp", profile_id="agent_x", limit=None
            )

        report = json.loads((reports_dir / "latest.json").read_text())
        assert report["judge_model"] == "deepseek/deepseek-chat"
        assert report["agent_model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_run_memory_ab_builds_two_arms(self, tmp_path: Path) -> None:
        """Both executors share benchmark_mode; memory_on gets an isolated volume."""
        import app.core.eval.memory_ab as memory_ab_mod

        captured_executors: dict[str, LocalEvalExecutor] = {}

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                captured_executors.update(executors)
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, cases, **kwargs):
                from myrm_agent_harness.eval import MatrixResult

                return MatrixResult(profile_ids=["memory_off", "memory_on"], cases=[])

        cases = [MagicMock()]
        cases[0].turns = [MagicMock()]

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "reports"
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = tmp_path / "memory"

        with (
            patch(
                "app.core.eval.memory_ab._memory_ab_state",
                {"is_running": False, "abort_requested": False},
            ),
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=(cases, {"msg": "seed"}, True),
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(return_value="unknown"),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                AsyncMock(),
            ),
        ):
            await memory_ab_mod.run_memory_ab_background("wb-bench-code")

        assert set(captured_executors) == {"memory_off", "memory_on"}
        off_executor = captured_executors["memory_off"]
        on_executor = captured_executors["memory_on"]
        assert off_executor.benchmark_mode is True
        assert off_executor._enable_memory is False
        assert on_executor.benchmark_mode is True
        assert on_executor._enable_memory is True
        assert on_executor._memory_base_path is not None
        assert Path(str(on_executor._memory_base_path)).is_relative_to(tmp_path)


@pytest.mark.asyncio
async def test_memory_ab_report_records_memory_tool_calls(tmp_path: Path) -> None:
    """Each arm's per_profile summary records how many memory_* tools were actually called."""
    from myrm_agent_harness.eval.protocols import AgentResponse

    import app.core.eval.memory_ab as memory_ab_mod

    class FakeTurn:
        def __init__(self, tools_called: list[str | dict[str, object]]) -> None:
            self.response = AgentResponse(answer="ok", tools_called=tools_called)

    class FakeArmResult:
        def __init__(self, turns: list[FakeTurn]) -> None:
            self.turn_results = turns

    class FakeMatrixResult:
        per_profile_results = {
            # memory-off arm never binds memory tools, so zero memory calls.
            "memory_off": FakeArmResult(
                [FakeTurn(["web_search_tool", "open_url_tool"])]
            ),
            # memory-on arm engages memory: str + dict-name forms both count.
            "memory_on": FakeArmResult(
                [
                    FakeTurn(["memory_search_tool", "web_search_tool"]),
                    FakeTurn([{"name": "memory_save_tool"}]),
                ]
            ),
        }

        def to_dict(self) -> dict[str, object]:
            return {
                "profile_ids": ["memory_off", "memory_on"],
                "total_cases": 1,
                "per_profile": {
                    "memory_off": {"pass_count": 1, "pass_rate": 1.0},
                    "memory_on": {"pass_count": 1, "pass_rate": 1.0},
                },
            }

    cases = [MagicMock()]
    cases[0].turns = [MagicMock()]

    reports_dir = tmp_path / "reports"
    memory_dir = tmp_path / "memory"
    memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
    memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = memory_dir

    class FakeMatrixRunner:
        def __init__(self, executors, **kwargs):
            self.kwargs = kwargs

        def abort(self) -> None:
            pass

        async def run_multi_turn(self, cases, **kwargs):
            return FakeMatrixResult()

    with (
        patch(
            "app.core.eval.memory_ab._memory_ab_state",
            {"is_running": False, "abort_requested": False},
        ),
        patch(
            "app.core.eval.benchmarks.build_benchmark_cases",
            return_value=(cases, {}, False),
        ),
        patch(
            "app.core.eval.model_config._resolve_agent_model_label",
            new=AsyncMock(return_value="unknown"),
        ),
        patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
        patch(
            "app.core.memory.adapters.setup.evict_cached_memory_manager", AsyncMock()
        ),
    ):
        await memory_ab_mod.run_memory_ab_background("wb-bench-code")

    report = json.loads((reports_dir / "latest.json").read_text())
    assert report["per_profile"]["memory_off"]["memory_tool_calls"] == 0
    assert report["per_profile"]["memory_on"]["memory_tool_calls"] == 2


app = build_minimal_app(preset="eval")


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


def test_memory_ab_router_endpoints(client: TestClient) -> None:
    from app.core.eval.wb_bench import WB_BENCH_SUBSETS

    subset_id = next(iter(WB_BENCH_SUBSETS))
    benchmark_id = f"wb-bench-{subset_id}"

    # already running
    with patch(
        "app.api.eval.memory_ab_router.get_memory_ab_status", return_value={"is_running": True}
    ):
        res = client.post("/api/v1/eval/memory-ab/run", json={"benchmark_id": benchmark_id})
        assert res.json()["status"] == "already_running"

    # unknown benchmark
    with patch(
        "app.api.eval.memory_ab_router.get_memory_ab_status", return_value={"is_running": False}
    ):
        res = client.post("/api/v1/eval/memory-ab/run", json={"benchmark_id": "nope"})
        assert res.json()["status"] == "error"

    # limit below 1 is rejected by the schema
    res = client.post(
        "/api/v1/eval/memory-ab/run",
        json={"benchmark_id": benchmark_id, "limit": 0},
    )
    assert res.status_code == 422

    # started → background task receives benchmark_id + profile_id
    with (
        patch(
            "app.api.eval.memory_ab_router.get_memory_ab_status",
            return_value={"is_running": False},
        ),
        patch(
            "app.services.agent.platform_config.verify_platform_embedding_ready",
            new=AsyncMock(),
        ),
        patch("app.api.eval.memory_ab_router.run_memory_ab_background") as mock_bg,
    ):
        res = client.post(
            "/api/v1/eval/memory-ab/run",
            json={"benchmark_id": benchmark_id, "profile_id": "agent_abc"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "started"
        _, call_kwargs = mock_bg.call_args
        assert call_kwargs["benchmark_id"] == benchmark_id
        assert call_kwargs["profile_id"] == "agent_abc"

    # missing embedding → explicit error, background task not started
    from myrm_agent_harness.api.config import ConfigIncompleteError

    with (
        patch(
            "app.api.eval.memory_ab_router.get_memory_ab_status",
            return_value={"is_running": False},
        ),
        patch(
            "app.services.agent.platform_config.verify_platform_embedding_ready",
            side_effect=ConfigIncompleteError(
                user_friendly_message={
                    "en": (
                        "Embedding model is not configured. Set it in Settings "
                        "> Retrieval."
                    )
                },
                technical_details="missing embedding config",
                resolution_steps=["Configure an embedding provider"],
                error_code="embedding_not_configured",
            ),
        ) as mock_req,
        patch("app.api.eval.memory_ab_router.run_memory_ab_background") as mock_bg,
    ):
        res = client.post(
            "/api/v1/eval/memory-ab/run", json={"benchmark_id": benchmark_id}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "error"
        assert "Embedding" in res.json()["error"]
        mock_req.assert_awaited_once()
        mock_bg.assert_not_called()

    # embedding configured but unreachable → explicit error, task not started
    with (
        patch(
            "app.api.eval.memory_ab_router.get_memory_ab_status",
            return_value={"is_running": False},
        ),
        patch(
            "app.services.agent.platform_config.verify_platform_embedding_ready",
            side_effect=ConfigIncompleteError(
                user_friendly_message={
                    "en": (
                        "Embedding model is configured but unreachable. Check "
                        "the model name and API key in Settings > Retrieval."
                    )
                },
                technical_details="embedding probe failed",
                resolution_steps=[
                    "Verify the model name and API key",
                    "Verify the provider endpoint is reachable",
                ],
                error_code="embedding_unavailable",
            ),
        ) as mock_verify,
        patch("app.api.eval.memory_ab_router.run_memory_ab_background") as mock_bg,
    ):
        res = client.post(
            "/api/v1/eval/memory-ab/run", json={"benchmark_id": benchmark_id}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "error"
        assert "unreachable" in res.json()["error"]
        mock_verify.assert_awaited_once()
        mock_bg.assert_not_called()

    # a run started while the probe was in flight → already_running (the
    # post-probe re-check closes the concurrent-start window)
    with (
        patch(
            "app.api.eval.memory_ab_router.get_memory_ab_status",
            side_effect=[
                {"is_running": False},
                {"is_running": True, "stage": "downloading"},
            ],
        ),
        patch(
            "app.services.agent.platform_config.verify_platform_embedding_ready",
            new=AsyncMock(),
        ),
        patch("app.api.eval.memory_ab_router.run_memory_ab_background") as mock_bg,
    ):
        res = client.post(
            "/api/v1/eval/memory-ab/run", json={"benchmark_id": benchmark_id}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "already_running"
        mock_bg.assert_not_called()

    # BrowseComp requires web search in benchmark_mode; a missing search
    # provider must fail fast with guidance instead of a misleading 0-score
    # comparison on both memory arms (mirrors the benchmark-run pre-flight).
    with (
        patch(
            "app.api.eval.memory_ab_router.get_memory_ab_status",
            return_value={"is_running": False},
        ),
        patch(
            "app.services.agent.platform_config.verify_platform_embedding_ready",
            new=AsyncMock(),
        ),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
        ) as mock_load_configs,
        patch("app.api.eval.memory_ab_router.run_memory_ab_background") as mock_bg,
    ):
        configs = SimpleNamespace(search_is_user_configured=False, search_cfg=None)
        mock_load_configs.return_value = configs
        res = client.post(
            "/api/v1/eval/memory-ab/run", json={"benchmark_id": "browsecomp"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "error"
        assert "requires web search" in res.json()["error"]
        mock_bg.assert_not_called()

    # A BrowseComp memory A/B with search+embedding ready but no resolvable
    # judge model must fail fast (both arms would otherwise score all-zero).
    with (
        patch(
            "app.api.eval.memory_ab_router.get_memory_ab_status",
            return_value={"is_running": False},
        ),
        patch(
            "app.services.agent.platform_config.verify_platform_embedding_ready",
            new=AsyncMock(),
        ),
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
        ) as mock_load_configs,
        patch(
            "app.core.channel_bridge.config_parsers.verify_search_service_available",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.core.eval.model_config._resolve_judge_config", return_value=(None, "none")
        ),
        patch("app.api.eval.memory_ab_router.run_memory_ab_background") as mock_bg,
    ):
        configs = SimpleNamespace(search_is_user_configured=True, search_cfg=object())
        mock_load_configs.return_value = configs
        res = client.post(
            "/api/v1/eval/memory-ab/run", json={"benchmark_id": "browsecomp"}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "error"
        assert "no model provider is configured" in res.json()["error"]
        mock_bg.assert_not_called()

    # abort not running
    with patch("app.api.eval.memory_ab_router.abort_memory_ab", return_value=False):
        res = client.post("/api/v1/eval/memory-ab/abort")
        assert res.json()["status"] == "not_running"

    # abort running
    with patch("app.api.eval.memory_ab_router.abort_memory_ab", return_value=True):
        res = client.post("/api/v1/eval/memory-ab/abort")
        assert res.json()["status"] == "aborted"

    # status passthrough
    with patch(
        "app.api.eval.memory_ab_router.get_memory_ab_status", return_value={"is_running": False}
    ):
        res = client.get("/api/v1/eval/memory-ab/status")
        assert res.json()["is_running"] is False

    # SSE stream passthrough
    with patch(
        "app.api.eval.memory_ab_router.get_memory_ab_status", return_value={"is_running": False}
    ):
        res = client.get("/api/v1/eval/memory-ab/stream")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

    # report not found
    with patch("app.api.eval.memory_ab_router.get_latest_memory_ab_report", return_value=None):
        res = client.get("/api/v1/eval/memory-ab/reports/latest")
        assert res.json()["status"] == "not_found"

    # report found
    with patch(
        "app.api.eval.memory_ab_router.get_latest_memory_ab_report",
        return_value={"profile_ids": []},
    ):
        res = client.get("/api/v1/eval/memory-ab/reports/latest")
        assert res.status_code == 200
        assert res.json()["status"] == "success"


@pytest.mark.asyncio
async def test_verify_platform_embedding_ready_probe_success() -> None:
    """Readiness check returns the embedding config when the probe succeeds."""
    from myrm_agent_harness.toolkits.retriever.embedding.factory import (
        EmbeddingConfig,
    )

    from app.services.agent.platform_config import (
        verify_platform_embedding_ready,
    )

    cfg = EmbeddingConfig(model="text-embedding-3-small", api_key="test-key")
    mock_service = MagicMock()
    mock_service.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])

    with (
        patch(
            "app.services.agent.platform_config.require_platform_embedding_config",
            new=AsyncMock(return_value=cfg),
        ),
        patch(
            "myrm_agent_harness.toolkits.retriever.embedding.factory.get_embedding_service",
            return_value=mock_service,
        ),
    ):
        result = await verify_platform_embedding_ready()
    assert result is cfg
    mock_service.embed.assert_awaited_once_with("embedding readiness probe")


@pytest.mark.asyncio
async def test_verify_platform_embedding_ready_probe_failure() -> None:
    """Readiness check raises embedding_unavailable when the probe fails."""
    from myrm_agent_harness.api.config import ConfigIncompleteError
    from myrm_agent_harness.toolkits.retriever.embedding.factory import (
        EmbeddingConfig,
    )

    from app.services.agent.platform_config import (
        verify_platform_embedding_ready,
    )

    cfg = EmbeddingConfig(model="text-embedding-3-small", api_key="bad-key")
    mock_service = MagicMock()
    mock_service.embed = AsyncMock(side_effect=RuntimeError("404 model not found"))

    with (
        patch(
            "app.services.agent.platform_config.require_platform_embedding_config",
            new=AsyncMock(return_value=cfg),
        ),
        patch(
            "myrm_agent_harness.toolkits.retriever.embedding.factory.get_embedding_service",
            return_value=mock_service,
        ),
    ):
        with pytest.raises(ConfigIncompleteError) as excinfo:
            await verify_platform_embedding_ready()
    assert excinfo.value.error_code == "embedding_unavailable"
    assert "unreachable" in excinfo.value.user_friendly_message["en"]
    assert "404 model not found" in excinfo.value.technical_details


class TestMemoryAbReportHistory:
    """Verify the report history helpers return newest-first summaries."""

    def test_report_history_sorted_newest_first(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "memory_ab_report_1000.json").write_text(
            json.dumps(
                {
                    "timestamp": 1000,
                    "dataset_id": "wb-bench-code",
                    "judge_model": "none",
                    "agent_model": "deepseek/deepseek-chat",
                    "per_profile": {"memory_off": {"pass_rate": 0.5}},
                }
            )
        )
        (reports_dir / "memory_ab_report_2000.json").write_text(
            json.dumps(
                {
                    "timestamp": 2000,
                    "dataset_id": "wb-bench-research",
                    "judge_model": "deepseek/deepseek-chat",
                    "agent_model": "gpt-4o",
                    "per_profile": {"memory_off": {"pass_rate": 0.8}},
                }
            )
        )

        history = memory_ab_mod.get_memory_ab_report_history(reports_dir)
        assert [h["timestamp"] for h in history] == [2000, 1000]
        assert history[0]["dataset_id"] == "wb-bench-research"
        assert history[0]["judge_model"] == "deepseek/deepseek-chat"
        assert history[0]["agent_model"] == "gpt-4o"
        assert history[0]["per_profile"]["memory_off"]["pass_rate"] == 0.8
        assert history[1]["agent_model"] == "deepseek/deepseek-chat"

    def test_report_history_skips_corrupt_files(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "memory_ab_report_1000.json").write_text("{not json")
        (reports_dir / "memory_ab_report_2000.json").write_text(
            json.dumps({"timestamp": 2000})
        )

        history = memory_ab_mod.get_memory_ab_report_history(reports_dir)
        assert [h["timestamp"] for h in history] == [2000]

    def test_report_by_timestamp(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        data = {"timestamp": 42, "profile_ids": ["memory_off", "memory_on"]}
        (reports_dir / "memory_ab_report_42.json").write_text(json.dumps(data))
        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir

        assert memory_ab_mod.get_memory_ab_report(42) == data
        assert memory_ab_mod.get_memory_ab_report(43) is None


def test_memory_ab_router_report_history(client: TestClient) -> None:
    # history passthrough
    with patch(
        "app.api.eval.memory_ab_router.get_memory_ab_report_history",
        return_value=[{"timestamp": 2000, "dataset_id": "wb-bench-code"}],
    ):
        res = client.get("/api/v1/eval/memory-ab/reports/history")
        assert res.json()["status"] == "success"
        assert res.json()["reports"] == [
            {"timestamp": 2000, "dataset_id": "wb-bench-code"}
        ]

    # specific report found
    with patch(
        "app.api.eval.memory_ab_router.get_memory_ab_report", return_value={"profile_ids": []}
    ):
        res = client.get("/api/v1/eval/memory-ab/reports/123")
        assert res.status_code == 200
        assert res.json()["status"] == "success"

    # specific report not found
    with patch("app.api.eval.memory_ab_router.get_memory_ab_report", return_value=None):
        res = client.get("/api/v1/eval/memory-ab/reports/123")
        assert res.json()["status"] == "not_found"


class TestMemoryAbEdgeBranches:
    """Edge branches of the memory A/B state helpers and report readers."""

    def test_get_memory_ab_status_returns_snapshot(self) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        memory_ab_mod._memory_ab_state["case_completed"] = 5
        status = memory_ab_mod.get_memory_ab_status()
        assert status["case_completed"] == 5
        status["case_completed"] = 99
        assert memory_ab_mod._memory_ab_state["case_completed"] == 5

    def test_abort_not_running_returns_false(self) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        memory_ab_mod._memory_ab_state["is_running"] = False
        assert memory_ab_mod.abort_memory_ab() is False

    def test_abort_running_sets_flag_and_aborts_runner(self) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        memory_ab_mod._memory_ab_state["is_running"] = True
        memory_ab_mod._memory_ab_state["abort_requested"] = False
        runner = MagicMock()
        memory_ab_mod._active_memory_ab_runner = runner
        assert memory_ab_mod.abort_memory_ab() is True
        assert memory_ab_mod._memory_ab_state["abort_requested"] is True
        runner.abort.assert_called_once()
        memory_ab_mod._active_memory_ab_runner = None

    def test_abort_running_without_runner_still_succeeds(self) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        memory_ab_mod._memory_ab_state["is_running"] = True
        memory_ab_mod._active_memory_ab_runner = None
        assert memory_ab_mod.abort_memory_ab() is True
        memory_ab_mod._memory_ab_state["is_running"] = False

    @pytest.mark.asyncio
    async def test_abort_before_evaluation_stops_run(self, tmp_path: Path) -> None:
        """Abort during download aborts before evaluation starts."""
        import app.core.eval.memory_ab as memory_ab_mod

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "reports"
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = tmp_path / "memory"

        with (
            patch(
                "app.core.eval.memory_ab._memory_ab_state",
                {"is_running": True, "abort_requested": True},
            ),
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=([MagicMock()], {}, False),
            ),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                AsyncMock(),
            ),
        ):
            await memory_ab_mod.run_memory_ab_background("wb-bench-code")

        # No report should be written when aborted before evaluation.
        assert not (tmp_path / "reports").exists()

    @pytest.mark.asyncio
    async def test_run_records_abort_error(self, tmp_path: Path) -> None:
        """Non-abort failures surface in the error field and cleanup still runs."""
        import app.core.eval.memory_ab as memory_ab_mod

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "reports"
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = tmp_path / "memory"
        memory_ab_mod._memory_ab_state["is_running"] = False
        memory_ab_mod._memory_ab_state["abort_requested"] = False

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                side_effect=RuntimeError("download exploded"),
            ),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                AsyncMock(),
            ),
        ):
            await memory_ab_mod.run_memory_ab_background("wb-bench-code")

        assert memory_ab_mod._memory_ab_state["error"] == "download exploded"
        assert memory_ab_mod._memory_ab_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_runner_failure_after_abort_logs_info(self, tmp_path: Path) -> None:
        """A runner exception following a user abort logs info, not an error."""
        import app.core.eval.memory_ab as memory_ab_mod

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, cases, **kwargs):
                # The user aborts while the runner is in flight; the subsequent
                # exception is treated as part of the abort, not a real failure.
                memory_ab_mod._memory_ab_state["abort_requested"] = True
                raise RuntimeError("aborted mid-run")

        cases = [MagicMock()]
        cases[0].turns = [MagicMock()]

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "reports"
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = tmp_path / "memory"

        with (
            patch(
                "app.core.eval.memory_ab._memory_ab_state",
                {"is_running": True, "abort_requested": False},
            ),
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=(cases, {}, False),
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(return_value="unknown"),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch("app.core.eval.memory_ab.logger.info") as mock_info,
            patch("app.core.eval.memory_ab.logger.exception") as mock_exc,
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                AsyncMock(),
            ),
        ):
            await memory_ab_mod.run_memory_ab_background("wb-bench-code")
            assert memory_ab_mod._memory_ab_state.get("error") is None
            assert memory_ab_mod._memory_ab_state["is_running"] is False

        mock_info.assert_called()
        mock_exc.assert_not_called()

    def test_latest_report_missing_dir(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "absent"
        assert memory_ab_mod.get_latest_memory_ab_report() is None

    def test_latest_report_non_object(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text('["not", "an", "object"]')
        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        assert memory_ab_mod.get_latest_memory_ab_report() is None

    def test_latest_report_returns_object(self, tmp_path: Path) -> None:
        """A valid object report is returned verbatim."""
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text('{"profile_ids": ["memory_off"]}')
        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        assert memory_ab_mod.get_latest_memory_ab_report() == {
            "profile_ids": ["memory_off"]
        }

    def test_latest_report_corrupt(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text("{broken")
        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        assert memory_ab_mod.get_latest_memory_ab_report() is None

    def test_report_by_timestamp_non_object(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "memory_ab_report_7.json").write_text("[1, 2]")
        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        assert memory_ab_mod.get_memory_ab_report(7) is None

    def test_report_by_timestamp_corrupt(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "memory_ab_report_7.json").write_text("{oops")
        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        assert memory_ab_mod.get_memory_ab_report(7) is None

    def test_report_history_missing_dir_returns_empty(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        assert memory_ab_mod.get_memory_ab_report_history(tmp_path / "absent") == []

    def test_report_history_skips_non_object(self, tmp_path: Path) -> None:
        import app.core.eval.memory_ab as memory_ab_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "memory_ab_report_1.json").write_text("[1]")
        history = memory_ab_mod.get_memory_ab_report_history(reports_dir)
        assert history == []


class TestCleanupResilience:
    """The finally-block teardown must never skip eval workspace cleanup."""

    @pytest.mark.asyncio
    async def test_evict_failure_still_cleans_workspaces(
        self, tmp_path: Path
    ) -> None:
        """A throwing evict_cached_memory_manager must not skip workspace cleanup.

        The finally block guards each teardown step independently so a failure
        in the memory-volume eviction cannot leave eval session workspaces
        behind (the exact leak this feature exists to prevent).
        """
        import app.core.eval.memory_ab as memory_ab_mod

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, cases, **kwargs):
                return MagicMock()

        from app.core.eval.executor import LocalEvalExecutor

        captured_executors: dict[str, LocalEvalExecutor] = {}

        def capturing_factory(*args: object, **kwargs: object) -> LocalEvalExecutor:
            executor = LocalEvalExecutor(*args, **kwargs)
            arm = kwargs.get("enable_memory")
            captured_executors["memory_on" if arm else "memory_off"] = executor
            return executor

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "reports"
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = tmp_path / "memory"
        memory_ab_mod._memory_ab_state["is_running"] = False
        memory_ab_mod._memory_ab_state["abort_requested"] = False

        async def failing_evict(*args: object, **kwargs: object) -> None:
            raise RuntimeError("evict exploded")

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=([MagicMock()], {}, False),
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(return_value="unknown"),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.eval.memory_ab.LocalEvalExecutor",
                side_effect=capturing_factory,
            ),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                side_effect=failing_evict,
            ),
        ):
            await memory_ab_mod.run_memory_ab_background("wb-bench-code")

        # Both arms' executors ran cleanup even though eviction failed.
        for executor in captured_executors.values():
            assert executor._created_workspaces == set()
            assert executor._session_id is None

    @pytest.mark.asyncio
    async def test_executor_cleanup_failure_does_not_block_other_arm(
        self, tmp_path: Path
    ) -> None:
        """One arm's cleanup throwing must not skip the other arm's cleanup."""
        import app.core.eval.memory_ab as memory_ab_mod

        from app.core.eval.executor import LocalEvalExecutor

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, cases, **kwargs):
                return MagicMock()

        cleaned: list[str] = []
        original_cleanup = LocalEvalExecutor.cleanup

        async def flaky_cleanup(self: LocalEvalExecutor) -> None:
            if not cleaned:
                # First arm's cleanup explodes; the second must still run.
                cleaned.append("boom")
                raise RuntimeError("cleanup exploded")
            cleaned.append("ok")
            await original_cleanup(self)

        memory_ab_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "reports"
        memory_ab_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = tmp_path / "memory"
        memory_ab_mod._memory_ab_state["is_running"] = False
        memory_ab_mod._memory_ab_state["abort_requested"] = False

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=([MagicMock()], {}, False),
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(return_value="unknown"),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch.object(LocalEvalExecutor, "cleanup", flaky_cleanup),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                new=AsyncMock(),
            ),
        ):
            await memory_ab_mod.run_memory_ab_background("wb-bench-code")

        assert cleaned == ["boom", "ok"]
