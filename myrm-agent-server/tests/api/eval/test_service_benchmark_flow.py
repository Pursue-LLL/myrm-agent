"""Unit tests for the generic benchmark background flows in eval service.

Covers ``run_benchmark_background`` / ``run_benchmark_download_background``
(download progress, abort, failure, state initialization), the live-suite
progress callback, and the latest.jsonl replace branch. All network and
runner execution is mocked so tests run fully offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.eval import service as service_mod
from app.core.eval.service import (
    get_eval_status,
    run_benchmark_background,
    run_benchmark_download_background,
    run_eval_suite,
)


class FakeJsonlReporter:
    """Writes a real file so the suite's copy2/latest steps can run."""

    def __init__(self, report_path: Path) -> None:
        self.report_path = Path(report_path)

    def report(self, result: object) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(
            json.dumps(
                {
                    "type": "summary",
                    "total_cases": getattr(result, "total_cases", 0),
                    "pass_rate": getattr(result, "pass_rate", 0.0),
                }
            )
            + "\n"
        )


@pytest.fixture(autouse=True)
def _reset_eval_state() -> None:
    service_mod._eval_state.clear()
    service_mod._eval_state.update(
        {
            "is_running": False,
            "total": 0,
            "completed": 0,
            "error": None,
            "abort_requested": False,
        }
    )
    service_mod._active_runner = None
    yield
    service_mod._eval_state["is_running"] = False
    service_mod._active_runner = None


def _mark_running() -> None:
    service_mod._eval_state["is_running"] = True


class TestRunBenchmarkBackground:
    @pytest.mark.asyncio
    async def test_runs_suite_with_sampled_cases(self) -> None:
        """Full flow: download progress reported, suite scheduled with sampled size."""
        _mark_running()
        case = MagicMock(metadata={}, turns=[object()])

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
            return ([case], {"seed-key": "seed-dir"}, True)

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                side_effect=fake_build,
            ),
            patch(
                "app.core.eval.benchmarks.benchmark_required_tools",
                return_value=("web_search",),
            ),
            patch("app.core.eval.service.run_eval_suite", new=AsyncMock()) as mock_run,
        ):
            await run_benchmark_background(
                "browse-comp",
                reports_dir=Path("/tmp/r"),
                profile_id="builder",
                benchmark_mode=True,
                stage_label="stage-x",
                limit=5,
            )

        assert service_mod._eval_state["download_progress"] == {
            "downloaded_bytes": 10,
            "total_bytes": 20,
        }
        assert service_mod._eval_state["is_running"] is False
        assert service_mod._eval_state["stage"] is None
        mock_run.assert_awaited_once()
        kwargs = mock_run.await_args.kwargs
        assert kwargs["dataset_id"] == "browse-comp"
        assert kwargs["external_cases"] == [case]
        assert kwargs["workspace_seed_map"] == {"seed-key": "seed-dir"}
        assert kwargs["benchmark_tools"] == ("web_search",)
        assert kwargs["limit"] == 5

    @pytest.mark.asyncio
    async def test_full_run_without_sample(self) -> None:
        """A limit at/above the full count is not recorded as a sample."""
        _mark_running()

        def fake_build(
            benchmark_id: str,
            *,
            limit: int | None = None,
            progress_callback: object = None,
            should_abort: object = None,
        ) -> tuple[list[object], dict[str, str], bool]:
            return ([], {}, False)

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                side_effect=fake_build,
            ),
            patch("app.core.eval.service.run_eval_suite", new=AsyncMock()) as mock_run,
        ):
            await run_benchmark_background("browse-comp", limit=10)

        assert mock_run.await_args.kwargs["limit"] is None

    @pytest.mark.asyncio
    async def test_abort_before_evaluation(self) -> None:
        """Abort requested during the build phase stops before scheduling."""
        _mark_running()
        service_mod._eval_state["abort_requested"] = True

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=([MagicMock()], {}, False),
            ),
            patch("app.core.eval.service.run_eval_suite", new=AsyncMock()) as mock_run,
            patch("app.core.eval.service.logger.info") as mock_info,
        ):
            await run_benchmark_background("browse-comp")

        mock_run.assert_not_awaited()
        mock_info.assert_called()
        assert service_mod._eval_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_build_failure_records_error(self) -> None:
        """A build exception surfaces through the global error state."""
        _mark_running()

        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                side_effect=RuntimeError("kaboom"),
            ),
            patch("app.core.eval.service.run_eval_suite", new=AsyncMock()),
            patch("app.core.eval.service.logger.exception") as mock_exc,
        ):
            await run_benchmark_background("browse-comp")

        assert service_mod._eval_state["error"] == "kaboom"
        assert service_mod._eval_state["is_running"] is False
        mock_exc.assert_called()

    @pytest.mark.asyncio
    async def test_init_state_when_not_pre_initialized(self) -> None:
        """Direct callers without router pre-init get the state bootstrapped."""
        with (
            patch(
                "app.core.eval.benchmarks.build_benchmark_cases",
                return_value=([], {}, False),
            ),
            patch("app.core.eval.service.run_eval_suite", new=AsyncMock()),
        ):
            await run_benchmark_background("browse-comp", stage_label="x")

        assert service_mod._eval_state["is_running"] is False
        assert service_mod._eval_state["stage"] is None


class TestRunBenchmarkDownload:
    @pytest.mark.asyncio
    async def test_download_reports_progress(self) -> None:
        _mark_running()

        def fake_ensure(
            benchmark_id: str,
            *,
            progress_callback: object = None,
            should_abort: object = None,
        ) -> Path:
            progress_callback(5, 8)
            assert should_abort() is False
            return Path("/x")

        with patch(
            "app.core.eval.benchmarks.ensure_benchmark_source",
            side_effect=fake_ensure,
        ):
            await run_benchmark_download_background("browse-comp", stage_label="s")

        assert service_mod._eval_state["download_progress"] == {
            "downloaded_bytes": 5,
            "total_bytes": 8,
        }
        assert service_mod._eval_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_download_abort_is_quiet(self) -> None:
        _mark_running()
        service_mod._eval_state["abort_requested"] = True

        with (
            patch(
                "app.core.eval.benchmarks.ensure_benchmark_source",
                side_effect=RuntimeError("stopped"),
            ),
            patch("app.core.eval.service.logger.info") as mock_info,
        ):
            await run_benchmark_download_background("browse-comp")

        mock_info.assert_called()
        assert service_mod._eval_state["error"] is None
        assert service_mod._eval_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_download_failure_records_error(self) -> None:
        _mark_running()

        with (
            patch(
                "app.core.eval.benchmarks.ensure_benchmark_source",
                side_effect=RuntimeError("network down"),
            ),
            patch("app.core.eval.service.logger.exception"),
        ):
            await run_benchmark_download_background("browse-comp")

        assert service_mod._eval_state["error"] == "network down"
        assert service_mod._eval_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_download_init_state_when_not_pre_initialized(self) -> None:
        with patch(
            "app.core.eval.benchmarks.ensure_benchmark_source",
            return_value=Path("/x"),
        ):
            await run_benchmark_download_background("browse-comp")

        assert service_mod._eval_state["is_running"] is False


class TestEvalStatus:
    @pytest.mark.asyncio
    async def test_get_eval_status_returns_snapshot(self) -> None:
        _mark_running()
        snapshot = get_eval_status()
        snapshot["is_running"] = False
        assert service_mod._eval_state["is_running"] is True


class TestSuiteProgressCallback:
    @pytest.mark.asyncio
    async def test_on_case_complete_increments_progress(self, tmp_path: Path) -> None:
        class FakeResult:
            total_cases = 2
            pass_count = 2
            fail_count = 0
            error_count = 0
            skip_count = 0
            pass_rate = 1.0
            all_passed = True
            total_ms = 5
            avg_pass_rate: float | None = None

        async def fake_run(cases: list[object], manifest: object) -> object:
            on_case_complete = mock_runner_cls.call_args.kwargs["on_case_complete"]
            on_case_complete(MagicMock())
            on_case_complete(MagicMock())
            return FakeResult()

        with (
            patch(
                "app.core.eval.service.get_dataset_path",
                return_value=tmp_path / "missing.jsonl",
            ),
            patch(
                "app.core.eval.service._build_eval_manifest",
                new=AsyncMock(return_value=MagicMock(to_dict=lambda: {"x": 1})),
            ),
            patch(
                "app.core.eval.executor.LocalEvalExecutor", return_value=MagicMock()
            ),
            patch("app.core.eval.service.EvalRunner") as mock_runner_cls,
            patch(
                "app.core.eval.service.JsonlReporter", FakeJsonlReporter
            ),
            patch(
                "myrm_agent_harness.eval.load_multi_turn_cases",
                return_value=[],
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.run_multi_turn = AsyncMock(side_effect=fake_run)
            mock_runner_cls.return_value = mock_runner

            await run_eval_suite(dataset_id="ds", reports_dir=tmp_path / "r")

        assert service_mod._eval_state["completed"] == 2


class TestLatestReportReplace:
    @pytest.mark.asyncio
    async def test_suite_replaces_existing_latest(self, tmp_path: Path) -> None:
        """A previous latest.jsonl is removed before the new report is copied."""
        class FakeResult:
            total_cases = 1
            pass_count = 1
            fail_count = 0
            error_count = 0
            skip_count = 0
            pass_rate = 1.0
            all_passed = True
            total_ms = 1
            avg_pass_rate: float | None = None

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir(parents=True)
        latest = reports_dir / "latest.jsonl"
        latest.write_text("stale\n")

        with (
            patch(
                "app.core.eval.service.get_dataset_path",
                return_value=tmp_path / "missing.jsonl",
            ),
            patch(
                "app.core.eval.service._build_eval_manifest",
                new=AsyncMock(return_value=MagicMock(to_dict=lambda: {"x": 1})),
            ),
            patch(
                "app.core.eval.executor.LocalEvalExecutor", return_value=MagicMock()
            ),
            patch("app.core.eval.service.EvalRunner") as mock_runner_cls,
            patch(
                "app.core.eval.service.JsonlReporter", FakeJsonlReporter
            ),
            patch(
                "myrm_agent_harness.eval.load_multi_turn_cases",
                return_value=[],
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.run_multi_turn = AsyncMock(return_value=FakeResult())
            mock_runner_cls.return_value = mock_runner

            await run_eval_suite(dataset_id="ds", reports_dir=reports_dir)

        replaced = latest.read_text()
        assert "stale" not in replaced
        assert "total_cases" in replaced
