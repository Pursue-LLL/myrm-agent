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

from app.core.eval.matrix import (
    _active_matrix_runner,
    _matrix_state,
    _run_matrix_eval,
    abort_matrix_eval,
    get_latest_matrix_report,
    get_matrix_eval_status,
    run_matrix_eval_background,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="eval")


@pytest.fixture(autouse=True)
def _reset_matrix_state() -> Generator[None, None, None]:
    """Reset the module-level matrix state between tests."""
    _matrix_state.clear()
    _matrix_state.update(
        {
            "is_running": False,
            "current_profile": None,
            "profile_progress": 0,
            "profile_total": 0,
            "case_completed": 0,
            "case_total": 0,
            "error": None,
        }
    )
    global _active_matrix_runner
    _active_matrix_runner = None
    yield
    _matrix_state["is_running"] = False
    _active_matrix_runner = None


class TestMatrixStateHelpers:
    def test_status_returns_snapshot(self) -> None:
        _matrix_state["case_completed"] = 3
        status = get_matrix_eval_status()
        assert status == _matrix_state
        # Mutating the snapshot must not affect the module state.
        status["case_completed"] = 99
        assert _matrix_state["case_completed"] == 3

    def test_abort_not_running_returns_false(self) -> None:
        assert abort_matrix_eval() is False

    def test_abort_running_aborts_active_runner(self) -> None:
        import app.core.eval.matrix as matrix_mod

        _matrix_state["is_running"] = True
        runner = MagicMock()
        matrix_mod._active_matrix_runner = runner
        assert abort_matrix_eval() is True
        runner.abort.assert_called_once()

    def test_abort_running_without_runner_still_succeeds(self) -> None:
        _matrix_state["is_running"] = True
        assert abort_matrix_eval() is True


class TestRunMatrixEvalBackground:
    @pytest.mark.asyncio
    async def test_skips_when_already_running(self) -> None:
        _matrix_state["is_running"] = True
        with patch(
            "app.core.eval.matrix._run_matrix_eval", new=AsyncMock()
        ) as mock_run:
            await run_matrix_eval_background(dataset_id="ds", profile_ids=["a", "b"])
        mock_run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_runs_and_clears_state(self) -> None:
        with patch(
            "app.core.eval.matrix._run_matrix_eval",
            new=AsyncMock(return_value={"profile_ids": ["a", "b"]}),
        ) as mock_run:
            await run_matrix_eval_background(
                dataset_id="ds", profile_ids=["a", "b"], benchmark_mode=True
            )
        mock_run.assert_awaited_once_with(
            "ds", ["a", "b"], benchmark_mode=True
        )
        assert _matrix_state["is_running"] is False
        assert _active_matrix_runner is None

    @pytest.mark.asyncio
    async def test_records_error_on_failure(self) -> None:
        with patch(
            "app.core.eval.matrix._run_matrix_eval",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await run_matrix_eval_background(dataset_id="ds", profile_ids=["a", "b"])
        assert _matrix_state["is_running"] is False
        assert _matrix_state["error"] == "boom"


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
        import app.core.eval.matrix as matrix_mod

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
        matrix_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir
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
        ):
            result = await _run_matrix_eval(
                dataset_id="ds", profile_ids=["a", "b"], benchmark_mode=True
            )

        assert result["profile_ids"] == ["a", "b"]
        assert result["timestamp"] > 0
        assert result["dataset_id"] == "ds"
        assert result["benchmark_mode"] is True

        # Progress callbacks drive the live state for the SSE stream.
        assert _matrix_state["current_profile"] == "b"
        assert _matrix_state["case_completed"] == 2

        report_files = sorted(reports_dir.glob("matrix_report_*.json"))
        assert len(report_files) == 1
        latest = reports_dir / "latest.json"
        assert latest.exists()
        assert "stale" not in latest.read_text()

    @pytest.mark.asyncio
    async def test_abort_finishes_with_partial_state(self, tmp_path: Path) -> None:
        """Runner raising is propagated and state is not reset by core itself."""
        import app.core.eval.matrix as matrix_mod

        class FakeMatrixRunner:
            def __init__(self, executors, **kwargs):
                self.kwargs = kwargs

            def abort(self) -> None:
                pass

            async def run_multi_turn(self, multi_cases, **kwargs):
                raise RuntimeError("aborted mid-run")

        matrix_mod.DEFAULT_MATRIX_REPORTS_DIR = tmp_path / "reports"
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
        import app.core.eval.matrix as matrix_mod

        matrix_mod.DEFAULT_MATRIX_REPORTS_DIR = tmp_path / "none"
        assert get_latest_matrix_report() is None

    def test_returns_report_when_present(self, tmp_path: Path) -> None:
        import app.core.eval.matrix as matrix_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text('{"profile_ids": ["a"]}')
        matrix_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir

        report = get_latest_matrix_report()
        assert report == {"profile_ids": ["a"]}

    def test_returns_none_on_corrupt_file(self, tmp_path: Path) -> None:
        import app.core.eval.matrix as matrix_mod

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "latest.json").write_text("{not json")
        matrix_mod.DEFAULT_MATRIX_REPORTS_DIR = reports_dir

        assert get_latest_matrix_report() is None


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
            res = client.post(
                "/api/v1/eval/matrix/run", json={"profile_ids": ["a", "b"]}
            )
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
        with patch(
            "app.api.eval.matrix_router.get_latest_matrix_report", return_value=None
        ):
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
