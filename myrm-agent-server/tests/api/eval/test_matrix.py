"""Unit tests for Matrix Eval (cross-profile comparison) service and router.

Covers ``app.core.eval.matrix`` state/progress/abort/report helpers and the
``app.api.eval.matrix_router`` endpoints (run/abort/status/stream/report).
All runner execution is faked so tests run fully offline.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness import __version__ as harness_version

from app.core.eval._state import (
    active_matrix_runner,
    matrix_state,
)
from app.core.eval.layered import (
    DEFAULT_LAYER_SPECS,
    _run_layer_eval,
    layer_specs_to_meta,
    run_layer_eval_background,
)
from app.core.eval.matrix import (
    _run_matrix_eval,
    abort_matrix_eval,
    get_latest_matrix_report,
    get_matrix_eval_status,
    run_matrix_eval_background,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="eval")


@pytest.fixture(autouse=True)
def _resetmatrix_state() -> Generator[None, None, None]:
    """Reset the module-level matrix state between tests."""
    matrix_state.clear()
    matrix_state.update(
        {
            "is_running": False,
            "current_profile": None,
            "profile_progress": 0,
            "profile_total": 0,
            "case_completed": 0,
            "case_total": 0,
            "stage": None,
            "download_progress": None,
            "error": None,
        }
    )
    global active_matrix_runner
    active_matrix_runner = None
    yield
    matrix_state["is_running"] = False
    active_matrix_runner = None


class TestMatrixStateHelpers:
    def test_status_returns_snapshot(self) -> None:
        matrix_state["case_completed"] = 3
        status = get_matrix_eval_status()
        assert status == matrix_state
        # Mutating the snapshot must not affect the module state.
        status["case_completed"] = 99
        assert matrix_state["case_completed"] == 3

    def test_state_reset_includes_progress_keys(self) -> None:
        """Initial matrix_state must carry the progress keys so a fresh run
        never inherits a stale ``stage`` from a previous eval variant."""
        assert matrix_state["stage"] is None
        assert matrix_state["download_progress"] is None

    def test_abort_not_running_returns_false(self) -> None:
        assert abort_matrix_eval() is False

    def test_abort_running_aborts_active_runner(self) -> None:
        import app.core.eval._state as state_mod

        matrix_state["is_running"] = True
        runner = MagicMock()
        state_mod.active_matrix_runner = runner
        assert abort_matrix_eval() is True
        runner.abort.assert_called_once()

    def test_abort_running_without_runner_still_succeeds(self) -> None:
        matrix_state["is_running"] = True
        assert abort_matrix_eval() is True


class TestRunMatrixEvalBackground:
    @pytest.mark.asyncio
    async def test_skips_when_already_running(self) -> None:
        matrix_state["is_running"] = True
        with patch("app.core.eval.matrix._run_matrix_eval", new=AsyncMock()) as mock_run:
            await run_matrix_eval_background(dataset_id="ds", profile_ids=["a", "b"])
        mock_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_runs_and_clears_state(self) -> None:
        with patch(
            "app.core.eval.matrix._run_matrix_eval",
            new=AsyncMock(return_value={"profile_ids": ["a", "b"]}),
        ) as mock_run:
            await run_matrix_eval_background(dataset_id="ds", profile_ids=["a", "b"], benchmark_mode=True)
        mock_run.assert_awaited_once_with("ds", ["a", "b"], benchmark_mode=True)
        assert matrix_state["is_running"] is False
        assert active_matrix_runner is None

    @pytest.mark.asyncio
    async def test_records_error_on_failure(self) -> None:
        with patch(
            "app.core.eval.matrix._run_matrix_eval",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await run_matrix_eval_background(dataset_id="ds", profile_ids=["a", "b"])
        assert matrix_state["is_running"] is False
        assert matrix_state["error"] == "boom"


class TestRunMatrixEvalCore:
    @pytest.mark.asyncio
    async def test_requires_at_least_two_profiles(self, tmp_path: Path) -> None:
        with patch(
            "app.core.eval.matrix.get_dataset_path",
            return_value=tmp_path / "ds.jsonl",
        ):
            with pytest.raises(ValueError, match="at least 2 profile"):
                await _run_matrix_eval(dataset_id="ds", profile_ids=["solo"])

    @pytest.mark.asyncio
    async def test_raises_when_dataset_missing(self, tmp_path: Path) -> None:
        with patch(
            "app.core.eval.matrix.get_dataset_path",
            return_value=tmp_path / "missing.jsonl",
        ):
            with pytest.raises(FileNotFoundError, match="Dataset not found"):
                await _run_matrix_eval(dataset_id="ds", profile_ids=["a", "b"])

    @pytest.mark.asyncio
    async def test_full_flow_writes_report_and_latest(self, tmp_path: Path) -> None:
        """Happy path: runs MatrixRunner, writes timestamped + latest reports."""
        import app.core.eval._state as state_mod

        class FakeTurn:
            turns = ["t1"]

        cases = [FakeTurn()]

        class FakeMatrixResult:
            def to_dict(self) -> dict[str, object]:
                return {
                    "profile_ids": ["a", "b"],
                    "total_cases": 1,
                    "per_profile": {
                        "a": {"pass_rate": 0.5},
                        "b": {"pass_rate": 1.0},
                    },
                }

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.executors = executors
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, multi_cases, **kwargs):
                self.kwargs["on_profile_start"]("a", 0, 2)
                self.kwargs["on_profile_start"]("b", 1, 2)
                self.kwargs["on_case_complete"]("a", MagicMock())
                self.kwargs["on_case_complete"]("b", MagicMock())
                return FakeMatrixResult()

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text('{"stale": true}')
        state_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir
        ds_path = tmp_path / "ds.jsonl"
        ds_path.write_text('{"message": "hi"}\n')

        with (
            patch("app.core.eval.matrix.get_dataset_path", return_value=ds_path),
            patch(
                "myrm_agent_harness.eval.load_multi_turn_cases",
                return_value=cases,
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.eval.matrix.LocalEvalExecutor",
                return_value=AsyncMock(),
            ),
            patch(
                "app.core.eval.model_config._resolve_judge_config",
                new=AsyncMock(return_value=(MagicMock(), "openai/gpt-4o-mini")),
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(side_effect=lambda pid: f"model-{pid}"),
            ),
        ):
            result = await _run_matrix_eval(dataset_id="ds", profile_ids=["a", "b"], benchmark_mode=True)

        assert result["profile_ids"] == ["a", "b"]
        assert result["timestamp"] > 0
        assert result["dataset_id"] == "ds"
        assert result["benchmark_mode"] is True
        assert result["eval_type"] == "matrix"
        assert result["harness_version"] == harness_version
        # Judge model disclosed so later model switches stay traceable.
        assert result["judge_model"] == "openai/gpt-4o-mini"
        assert result["aborted"] is False
        # Per-profile model labels make the report self-contained.
        assert result["per_profile"]["a"]["agent_model"] == "model-a"
        assert result["per_profile"]["b"]["agent_model"] == "model-b"

        # Progress callbacks drive the live state for the SSE stream.
        assert matrix_state["current_profile"] == "b"
        assert matrix_state["case_completed"] == 2

        report_files = sorted(reports_dir.glob("matrix_report_*.json"))
        assert len(report_files) == 1
        latest = reports_dir / "latest.json"
        assert latest.exists()
        assert "stale" not in latest.read_text()

    @pytest.mark.asyncio
    async def test_abort_finishes_with_partial_state(self, tmp_path: Path) -> None:
        """Runner raising is propagated and state is not reset by core itself."""
        import app.core.eval._state as state_mod

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, multi_cases, **kwargs):
                raise RuntimeError("aborted mid-run")

        state_mod.DEFAULT_MATRIX_REPORTS_DIR = tmp_path / "reports"
        ds_path = tmp_path / "ds.jsonl"
        ds_path.write_text('{"message": "hi"}\n')

        with (
            patch("app.core.eval.matrix.get_dataset_path", return_value=ds_path),
            patch(
                "myrm_agent_harness.eval.load_multi_turn_cases",
                return_value=[MagicMock(turns=["t1"])],
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch("app.core.eval.matrix.LocalEvalExecutor", return_value=AsyncMock()),
        ):
            with pytest.raises(RuntimeError, match="aborted mid-run"):
                await _run_matrix_eval(dataset_id="ds", profile_ids=["a", "b"])


class TestGetLatestMatrixReport:
    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        import app.core.eval._state as state_mod

        state_mod.DEFAULT_MATRIX_REPORTS_DIR = tmp_path / "none"
        assert get_latest_matrix_report() is None

    def test_returns_report_when_present(self, tmp_path: Path) -> None:
        import app.core.eval._state as state_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text('{"profile_ids": ["a"]}')
        state_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir

        report = get_latest_matrix_report()
        assert report == {"profile_ids": ["a"]}

    def test_returns_none_on_corrupt_file(self, tmp_path: Path) -> None:
        import app.core.eval._state as state_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text("{not json")
        state_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir

        assert get_latest_matrix_report() is None


class TestMatrixReportHistory:
    def test_history_empty_when_dir_missing(self, tmp_path: Path) -> None:
        import app.core.eval._state as state_mod

        state_mod.DEFAULT_MATRIX_REPORTS_DIR = tmp_path / "absent"

        from app.core.eval.matrix import get_matrix_report_history

        assert get_matrix_report_history() == []

    def test_history_lists_reports_newest_first(self, tmp_path: Path) -> None:
        import app.core.eval._state as state_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "matrix_report_10.json").write_text(
            '{"timestamp": 10, "eval_type": "layered", "dataset_id": "ds-a", "stable_rate": 0.5, "aborted": false}'
        )
        (reports_dir / "matrix_report_20.json").write_text(
            '{"timestamp": 20, "eval_type": "matrix", "dataset_id": "ds-b", "stable_rate": 0.8}'
        )
        state_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir

        from app.core.eval.matrix import get_matrix_report_history

        history = get_matrix_report_history()
        assert [h["timestamp"] for h in history] == [20, 10]
        assert history[0]["eval_type"] == "matrix"
        assert history[0]["stable_rate"] == 0.8
        assert history[1]["eval_type"] == "layered"
        assert history[1]["aborted"] is False
        # The summary must stay lightweight — no per-case payload.
        assert "per_profile" not in history[0]
        assert "matrix" not in history[0]

    def test_history_skips_corrupt_and_non_matching_files(self, tmp_path: Path) -> None:
        import app.core.eval._state as state_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "matrix_report_1.json").write_text("{not json")
        (reports_dir / "matrix_report_2.json").write_text("[]")
        (reports_dir / "other.json").write_text('{"timestamp": 3}')
        state_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir

        from app.core.eval.matrix import get_matrix_report_history

        assert get_matrix_report_history() == []

    def test_get_report_by_timestamp(self, tmp_path: Path) -> None:
        import app.core.eval._state as state_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "matrix_report_7.json").write_text('{"timestamp": 7, "profile_ids": ["a"]}')
        state_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir

        from app.core.eval.matrix import get_matrix_report

        assert get_matrix_report(7) == {"timestamp": 7, "profile_ids": ["a"]}
        assert get_matrix_report(8) is None


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


class TestMatrixRouterEndpoints:
    def test_run_requires_two_profiles(self, client: TestClient) -> None:
        res = client.post("/api/v1/eval/matrix/run", json={"profile_ids": ["solo"]})
        assert res.status_code == 400

    def test_run_already_running(self, client: TestClient) -> None:
        with patch(
            "app.api.eval.matrix_router.get_matrix_eval_status",
            return_value={"is_running": True},
        ):
            res = client.post("/api/v1/eval/matrix/run", json={"profile_ids": ["a", "b"]})
        assert res.json()["status"] == "already_running"

    def test_run_starts_background(self, client: TestClient) -> None:
        with (
            patch(
                "app.api.eval.matrix_router.get_matrix_eval_status",
                return_value={"is_running": False},
            ),
            patch("app.api.eval.matrix_router.run_matrix_eval_background") as mock_bg,
        ):
            res = client.post(
                "/api/v1/eval/matrix/run",
                json={
                    "profile_ids": ["a", "b"],
                    "dataset_id": "ds",
                    "benchmark_mode": True,
                },
            )
        assert res.status_code == 200
        assert res.json()["status"] == "started"
        _, call_kwargs = mock_bg.call_args
        assert call_kwargs["profile_ids"] == ["a", "b"]
        assert call_kwargs["dataset_id"] == "ds"
        assert call_kwargs["benchmark_mode"] is True

    def test_abort_not_running(self, client: TestClient) -> None:
        with patch("app.api.eval.matrix_router.abort_matrix_eval", return_value=False):
            res = client.post("/api/v1/eval/matrix/abort")
        assert res.json()["status"] == "not_running"

    def test_abort_running(self, client: TestClient) -> None:
        with patch("app.api.eval.matrix_router.abort_matrix_eval", return_value=True):
            res = client.post("/api/v1/eval/matrix/abort")
        assert res.json()["status"] == "aborted"

    def test_status_passthrough(self, client: TestClient) -> None:
        with patch(
            "app.api.eval.matrix_router.get_matrix_eval_status",
            return_value={"is_running": True, "case_completed": 2},
        ):
            res = client.get("/api/v1/eval/matrix/status")
        assert res.json() == {"is_running": True, "case_completed": 2}

    def test_stream_passthrough(self, client: TestClient) -> None:
        with patch(
            "app.api.eval.matrix_router.get_matrix_eval_status",
            return_value={"is_running": False},
        ):
            res = client.get("/api/v1/eval/matrix/stream")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]

    def test_report_not_found(self, client: TestClient) -> None:
        with patch("app.api.eval.matrix_router.get_latest_matrix_report", return_value=None):
            res = client.get("/api/v1/eval/matrix/reports/latest")
        assert res.json()["status"] == "not_found"

    def test_report_found(self, client: TestClient) -> None:
        with patch(
            "app.api.eval.matrix_router.get_latest_matrix_report",
            return_value={"profile_ids": ["a", "b"]},
        ):
            res = client.get("/api/v1/eval/matrix/reports/latest")
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        assert res.json()["report"]["profile_ids"] == ["a", "b"]

    def test_history_returns_reports(self, client: TestClient) -> None:
        with patch(
            "app.api.eval.matrix_router.get_matrix_report_history",
            return_value=[{"timestamp": 2}, {"timestamp": 1}],
        ):
            res = client.get("/api/v1/eval/matrix/reports/history")
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        assert res.json()["reports"] == [{"timestamp": 2}, {"timestamp": 1}]

    def test_report_by_timestamp_not_found(self, client: TestClient) -> None:
        with patch("app.api.eval.matrix_router.get_matrix_report", return_value=None):
            res = client.get("/api/v1/eval/matrix/reports/123")
        assert res.json()["status"] == "not_found"

    def test_report_by_timestamp_found(self, client: TestClient) -> None:
        with patch(
            "app.api.eval.matrix_router.get_matrix_report",
            return_value={"timestamp": 123, "profile_ids": ["a"]},
        ):
            res = client.get("/api/v1/eval/matrix/reports/123")
        assert res.status_code == 200
        assert res.json()["status"] == "success"
        assert res.json()["report"]["timestamp"] == 123


class TestLayerRouterEndpoints:
    def test_layers_run_unknown_benchmark(self, client: TestClient) -> None:
        with (
            patch(
                "app.api.eval.matrix_router.get_matrix_eval_status",
                return_value={"is_running": False},
            ),
            patch("app.core.eval.benchmarks.is_known_benchmark", return_value=False),
        ):
            res = client.post(
                "/api/v1/eval/matrix/layers-run",
                json={"benchmark_id": "nope"},
            )
        assert res.json()["status"] == "error"
        assert "Unknown benchmark" in res.json()["error"]

    def test_layers_run_embedding_preflight_failure(self, client: TestClient) -> None:
        from myrm_agent_harness.api.config import ConfigIncompleteError

        with (
            patch(
                "app.api.eval.matrix_router.get_matrix_eval_status",
                return_value={"is_running": False},
            ),
            patch("app.core.eval.benchmarks.is_known_benchmark", return_value=True),
            patch(
                "app.services.agent.platform_config.verify_platform_embedding_ready",
                new=AsyncMock(
                    side_effect=ConfigIncompleteError(
                        user_friendly_message={"en": "Embedding not configured"},
                        technical_details="missing embedding config",
                        resolution_steps=["Configure an embedding provider"],
                        error_code="embedding_not_configured",
                    )
                ),
            ),
        ):
            res = client.post(
                "/api/v1/eval/matrix/layers-run",
                json={"benchmark_id": "wb-bench-code"},
            )
        assert res.json()["status"] == "error"
        assert res.json()["error"] == "Embedding not configured"

    def test_layers_run_starts_background(self, client: TestClient) -> None:
        with (
            patch(
                "app.api.eval.matrix_router.get_matrix_eval_status",
                return_value={"is_running": False},
            ),
            patch("app.core.eval.benchmarks.is_known_benchmark", return_value=True),
            patch(
                "app.services.agent.platform_config.verify_platform_embedding_ready",
                new=AsyncMock(),
            ),
            patch(
                "app.core.eval.benchmarks.benchmark_required_tools",
                return_value=(),
            ),
            patch(
                "app.core.eval.benchmarks.benchmark_needs_judge",
                return_value=False,
            ),
            patch("app.api.eval.matrix_router.run_layer_eval_background") as mock_bg,
        ):
            res = client.post(
                "/api/v1/eval/matrix/layers-run",
                json={"benchmark_id": "wb-bench-code", "profile_id": "p1", "limit": 3},
            )
        assert res.status_code == 200
        assert res.json()["status"] == "started"
        _, call_kwargs = mock_bg.call_args
        assert call_kwargs["benchmark_id"] == "wb-bench-code"
        assert call_kwargs["profile_id"] == "p1"
        assert call_kwargs["limit"] == 3

    def test_layers_run_rejects_zero_limit(self, client: TestClient) -> None:
        res = client.post(
            "/api/v1/eval/matrix/layers-run",
            json={"benchmark_id": "wb-bench-code", "limit": 0},
        )
        assert res.status_code == 422


class TestLayerSpecs:
    def test_default_chain_is_ascending_and_complete(self) -> None:
        assert [spec.key for spec in DEFAULT_LAYER_SPECS] == [
            "bare",
            "core",
            "skills",
            "memory",
        ]
        # Ascending: each layer adds exactly one capability switch.
        for prev, spec in zip(DEFAULT_LAYER_SPECS, DEFAULT_LAYER_SPECS[1:], strict=False):
            added = (spec.benchmark_mode, spec.skills_enabled, spec.memory_enabled) != (
                prev.benchmark_mode,
                prev.skills_enabled,
                prev.memory_enabled,
            )
            assert added
        # The final layer is the full (non-benchmark) profile configuration.
        final = DEFAULT_LAYER_SPECS[-1]
        assert final.benchmark_mode is False
        assert final.skills_enabled is True
        assert final.memory_enabled is True

    def test_fingerprint_stable_and_config_sensitive(self) -> None:
        fp_bare = DEFAULT_LAYER_SPECS[0].fingerprint()
        fp_core = DEFAULT_LAYER_SPECS[1].fingerprint()
        assert len(fp_bare) == 12
        assert fp_bare != fp_core
        # Deterministic across calls.
        assert DEFAULT_LAYER_SPECS[0].fingerprint() == fp_bare

    def test_layer_specs_to_meta_includes_fingerprints(self) -> None:
        meta = layer_specs_to_meta()
        assert [m["key"] for m in meta] == ["bare", "core", "skills", "memory"]
        assert all(isinstance(m["fingerprint"], str) for m in meta)
        assert meta[0]["benchmark_mode"] is True
        assert meta[-1]["memory_enabled"] is True


class TestRunLayerEvalBackground:
    @pytest.mark.asyncio
    async def test_skips_when_already_running(self) -> None:
        matrix_state["is_running"] = True
        with patch("app.core.eval.layered._run_layer_eval", new=AsyncMock()) as mock_run:
            await run_layer_eval_background("wb-bench-code")
        mock_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_runs_and_clears_state(self) -> None:
        with patch(
            "app.core.eval.layered._run_layer_eval",
            new=AsyncMock(return_value={"layers": []}),
        ) as mock_run:
            await run_layer_eval_background("wb-bench-code", profile_id="p1", limit=3)
        mock_run.assert_awaited_once_with("wb-bench-code", "p1", limit=3)
        assert matrix_state["is_running"] is False
        assert matrix_state["profile_total"] == len(DEFAULT_LAYER_SPECS)
        assert active_matrix_runner is None

    @pytest.mark.asyncio
    async def test_records_error_on_failure(self) -> None:
        with patch(
            "app.core.eval.layered._run_layer_eval",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await run_layer_eval_background("wb-bench-code")
        assert matrix_state["is_running"] is False
        assert matrix_state["error"] == "boom"


class TestRunLayerEvalCore:
    @pytest.mark.asyncio
    async def test_full_flow_writes_layered_report(self, tmp_path: Path) -> None:
        """Happy path: four executors, progress callbacks, layered report."""
        import app.core.eval._state as state_mod

        class FakeTurn:
            turns = ["t1"]

        cases = [FakeTurn()]

        class FakeMatrixResult:
            def to_dict(self) -> dict[str, object]:
                return {
                    "profile_ids": ["bare", "core", "skills", "memory"],
                    "total_cases": 1,
                    "per_profile": {
                        "bare": {"pass_rate": 0.0},
                        "core": {"pass_rate": 0.5},
                        "skills": {"pass_rate": 0.8},
                        "memory": {"pass_rate": 1.0},
                    },
                }

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.executors = executors
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, multi_cases, **kwargs):
                for idx, key in enumerate(["bare", "core", "skills", "memory"]):
                    self.kwargs["on_profile_start"](key, idx, 4)
                    self.kwargs["on_case_complete"](key, MagicMock())
                result = FakeMatrixResult()
                result.per_profile_results = {}
                for key in ["bare", "core", "skills", "memory"]:
                    turn = MagicMock()
                    turn.response.tools_called = ["memory_search"]
                    layer_result = MagicMock()
                    layer_result.turn_results = [turn]
                    result.per_profile_results[key] = layer_result
                return result

        import app.core.eval.layered as layered_mod

        reports_dir = tmp_path / "reports"
        state_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir
        layered_mod.DEFAULT_LAYERS_MEMORY_DIR = tmp_path / "layers_memory"

        executor_factories: list[dict[str, object]] = []

        def fake_executor_factory(**kwargs: object) -> MagicMock:
            executor_factories.append(kwargs)
            return AsyncMock()

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=(cases, {}, False),
            ),
            patch(
                "app.core.eval.benchmarks.benchmark_required_tools",
                return_value=("web_search",),
            ),
            patch(
                "app.core.eval.benchmarks.benchmark_needs_judge",
                return_value=True,
            ),
            patch(
                "app.core.eval.model_config._resolve_agent_model_label",
                new=AsyncMock(return_value="openai/gpt-4o"),
            ),
            patch(
                "app.core.eval.model_config._resolve_judge_config",
                new=AsyncMock(return_value=(MagicMock(), "openai/gpt-4o-mini")),
            ),
            patch("myrm_agent_harness.eval.MatrixRunner", FakeMatrixRunner),
            patch(
                "app.core.eval.layered.LocalEvalExecutor",
                side_effect=fake_executor_factory,
            ),
            patch(
                "app.core.memory.adapters.setup.evict_cached_memory_manager",
                new=AsyncMock(),
            ),
            patch("app.core.eval.layered.shutil.rmtree"),
        ):
            result = await _run_layer_eval("wb-bench-code", profile_id="p1", limit=2)

        assert result["dataset_id"] == "wb-bench-code"
        assert result["profile_id"] == "p1"
        assert result["agent_model"] == "openai/gpt-4o"
        assert result["judge_model"] == "openai/gpt-4o-mini"
        assert result["eval_type"] == "layered"
        assert result["harness_version"] == harness_version
        assert result["aborted"] is False
        assert [m["key"] for m in result["layers"]] == [
            "bare",
            "core",
            "skills",
            "memory",
        ]
        assert all("fingerprint" in m for m in result["layers"])
        # Each layer discloses how many times it actually invoked memory tools.
        assert all(isinstance(result["per_profile"][k]["memory_tool_calls"], int) for k in ["bare", "core", "skills", "memory"])

        # Four executors, one per layer, with the pinned switch combination.
        assert len(executor_factories) == 4
        keys = [f["benchmark_mode"] for f in executor_factories]
        assert keys == [True, False, False, False]
        skill_overrides = [f["skill_ids_override"] for f in executor_factories]
        assert skill_overrides == [[], [], None, None]
        memory_flags = [f["enable_memory"] for f in executor_factories]
        assert memory_flags == [False, False, False, True]
        # Layered ablation must not blend the user's real shared context into
        # any layer — every executor isolates shared-context injection.
        assert all(f["resolve_shared_contexts"] is False for f in executor_factories)

        # Progress callbacks drive the shared matrix state.
        assert matrix_state["current_profile"] == "memory"
        assert matrix_state["case_completed"] == 4

        latest = reports_dir / "latest.json"
        assert latest.exists()
        assert "stale" not in latest.read_text()

    @pytest.mark.asyncio
    async def test_abort_before_eval_returns_empty(self, tmp_path: Path) -> None:
        """Abort during download short-circuits before any executor runs."""
        import app.core.eval._state as state_mod

        state_mod.DEFAULT_MATRIX_REPORTS_DIR = tmp_path / "reports"
        matrix_state["abort_requested"] = True

        with patch(
            "app.core.eval.benchmarks.build_benchmark_cases",
            return_value=([MagicMock(turns=["t1"])], {}, True),
        ):
            result = await _run_layer_eval("wb-bench-code", None)
        assert result == {}
        assert matrix_state["case_total"] == 0
