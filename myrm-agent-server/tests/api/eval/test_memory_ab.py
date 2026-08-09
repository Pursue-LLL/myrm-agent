"""Tests for Memory A/B evaluation: executor params, service flow, router endpoints."""

import json
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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
        import app.core.eval.service as service_mod

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

        evict_mock = AsyncMock()
        reports_dir = tmp_path / "memory_ab_reports"
        memory_dir = tmp_path / "eval_memory_ab"

        service_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
        service_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = memory_dir

        with (
            patch(
                "app.core.eval.service._memory_ab_state",
                {"is_running": False, "abort_requested": False},
            ),
            patch(
                "app.core.eval.wb_bench.build_wb_bench_cases", return_value=(cases, {})
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager", evict_mock
            ),
        ):
            await service_mod.run_memory_ab_background("code", profile_id="agent_x")

        latest = reports_dir / "latest.json"
        assert latest.exists()
        report = latest.read_text()
        assert '"memory_off"' in report
        assert '"memory_on"' in report
        evict_mock.assert_awaited_once()
        assert not memory_dir.exists()

    @pytest.mark.asyncio
    async def test_run_memory_ab_builds_two_arms(self, tmp_path: Path) -> None:
        """Both executors share benchmark_mode; memory_on gets an isolated volume."""
        import app.core.eval.service as service_mod

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

        service_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = tmp_path / "reports"
        service_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = tmp_path / "memory"

        with (
            patch(
                "app.core.eval.service._memory_ab_state",
                {"is_running": False, "abort_requested": False},
            ),
            patch(
                "app.core.eval.wb_bench.build_wb_bench_cases",
                return_value=(cases, {"msg": "seed"}),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                AsyncMock(),
            ),
        ):
            await service_mod.run_memory_ab_background("code")

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

    import app.core.eval.service as service_mod

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
    service_mod.DEFAULT_MEMORY_AB_REPORTS_DIR = reports_dir
    service_mod.DEFAULT_MEMORY_AB_MEMORY_DIR = memory_dir

    class FakeMatrixRunner:
        def __init__(self, executors, **kwargs):
            self.kwargs = kwargs

        def abort(self) -> None:
            pass

        async def run_multi_turn(self, cases, **kwargs):
            return FakeMatrixResult()

    with (
        patch(
            "app.core.eval.service._memory_ab_state",
            {"is_running": False, "abort_requested": False},
        ),
        patch("app.core.eval.wb_bench.build_wb_bench_cases", return_value=(cases, {})),
        patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
        patch(
            "app.core.memory.adapters.setup.evict_cached_memory_manager", AsyncMock()
        ),
    ):
        await service_mod.run_memory_ab_background("code")

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

    # already running
    with patch(
        "app.api.eval.router.get_memory_ab_status", return_value={"is_running": True}
    ):
        res = client.post("/api/v1/eval/memory-ab/run", json={"subset_id": subset_id})
        assert res.json()["status"] == "already_running"

    # unknown subset
    with patch(
        "app.api.eval.router.get_memory_ab_status", return_value={"is_running": False}
    ):
        res = client.post("/api/v1/eval/memory-ab/run", json={"subset_id": "nope"})
        assert res.json()["status"] == "error"

    # started → background task receives subset_id + profile_id
    with (
        patch(
            "app.api.eval.router.get_memory_ab_status",
            return_value={"is_running": False},
        ),
        patch("app.api.eval.router.run_memory_ab_background") as mock_bg,
    ):
        res = client.post(
            "/api/v1/eval/memory-ab/run",
            json={"subset_id": subset_id, "profile_id": "agent_abc"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "started"
        _, call_kwargs = mock_bg.call_args
        assert call_kwargs["subset_id"] == subset_id
        assert call_kwargs["profile_id"] == "agent_abc"

    # abort not running
    with patch("app.api.eval.router.abort_memory_ab", return_value=False):
        res = client.post("/api/v1/eval/memory-ab/abort")
        assert res.json()["status"] == "not_running"

    # abort running
    with patch("app.api.eval.router.abort_memory_ab", return_value=True):
        res = client.post("/api/v1/eval/memory-ab/abort")
        assert res.json()["status"] == "aborted"

    # status passthrough
    with patch(
        "app.api.eval.router.get_memory_ab_status", return_value={"is_running": False}
    ):
        res = client.get("/api/v1/eval/memory-ab/status")
        assert res.json()["is_running"] is False

    # report not found
    with patch("app.api.eval.router.get_latest_memory_ab_report", return_value=None):
        res = client.get("/api/v1/eval/memory-ab/reports/latest")
        assert res.json()["status"] == "not_found"

    # report found
    with patch(
        "app.api.eval.router.get_latest_memory_ab_report",
        return_value={"profile_ids": []},
    ):
        res = client.get("/api/v1/eval/memory-ab/reports/latest")
        assert res.status_code == 200
        assert res.json()["status"] == "success"
