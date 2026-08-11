"""Unit tests for the eval service orchestration.

Covers ``app.core.eval.service`` background wrappers, the WorkBuddy Bench
abort/download branches, and the suite runner with faked harness executors.
All network/runner execution is mocked so tests run fully offline.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.eval import service as service_mod
from app.core.eval.manifest import _build_eval_manifest
from app.core.eval.service import (
    abort_eval,
    run_eval_suite,
    run_eval_suite_background,
    run_wb_bench_background,
    run_wb_bench_download_background,
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
        }
    )
    service_mod._active_runner = None
    yield
    service_mod._eval_state["is_running"] = False
    service_mod._active_runner = None


class TestBuildEvalManifest:
    @pytest.mark.asyncio
    async def test_manifest_without_profile(self, tmp_path: Path) -> None:
        from app.core.channel_bridge.config_loader import UserConfigs
        from app.core.types import ModelConfig

        configs = UserConfigs(
            model_cfg=ModelConfig(model="openai-like/gpt-test", api_key="x"),
            search_cfg=None,
            search_is_user_configured=False,
            retrieval_dict={},
            personal_settings_dict={},
            mcp_dict={},
            providers_dict={},
        )
        cases_path = tmp_path / "ds.jsonl"
        cases_path.write_text('{"message": "hi"}\n')

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=configs),
        ):
            manifest = await _build_eval_manifest(
                profile_id=None, dataset_id="ds", cases_path=cases_path
            )

        assert manifest.profile_id == "default"
        assert manifest.benchmark_mode is False
        assert manifest.task_set_id == "ds"
        assert manifest.task_set_hash != "empty"
        assert manifest.model_provider == "openai-like"
        assert manifest.model_id == "gpt-test"

    @pytest.mark.asyncio
    async def test_manifest_with_profile_and_external_cases(self) -> None:
        class FakeTurn:
            pass

        from app.core.channel_bridge.config_loader import UserConfigs
        from app.core.types import ModelConfig

        configs = UserConfigs(
            model_cfg=ModelConfig(model="openai-like/gpt-test", api_key="x"),
            search_cfg=None,
            search_is_user_configured=False,
            retrieval_dict={},
            personal_settings_dict={},
            mcp_dict={},
            providers_dict={},
        )

        class FakeProfile:
            model = "anthropic/claude-sonnet-4-20250514"
            engine_params = {"thinking_effort": "high", "max_tokens": 8192}
            enabled_builtin_tools = ("web_search", "file")
            system_prompt = "You are great"
            skill_ids = []
            subagent_ids = None
            security_overrides = None
            max_iterations = None
            memory_policy = None
            auto_restore_domains = []
            memory_decay_profile = None
            memory_extraction_preset = None
            mcp_ids = None
            mcp_tool_selections = None
            personality_style = None

        class FakeResolver:
            async def resolve(self, profile_id: str) -> FakeProfile:
                return FakeProfile()

        with (
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new=AsyncMock(return_value=configs),
            ),
            patch(
                "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
                return_value=FakeResolver(),
            ),
        ):
            manifest = await _build_eval_manifest(
                profile_id="builder",
                dataset_id="wb-bench-code",
                cases_path=Path("/nonexistent.jsonl"),
                benchmark_mode=True,
                external_cases=[FakeTurn()],
            )

        assert manifest.profile_id == "builder"
        assert manifest.benchmark_mode is True
        assert manifest.model_provider == "anthropic"
        assert manifest.model_id == "claude-sonnet-4-20250514"
        assert manifest.thinking_effort == "high"
        assert manifest.budget_max_tokens == 8192
        assert manifest.tool_policy == ("web_search", "file")
        assert manifest.prompt_fingerprint != "none"


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


class TestResolveAgentModelLabel:
    """Shared agent-model resolution: profile priority, config fallback, unknown."""

    @pytest.mark.asyncio
    async def test_falls_back_to_user_model_config(self) -> None:
        from app.core.channel_bridge.config_loader import UserConfigs
        from app.core.eval.model_config import _resolve_agent_model_label
        from app.core.types import ModelConfig

        configs = UserConfigs(
            model_cfg=ModelConfig(model="openai-like/gpt-test", api_key="x"),
            search_cfg=None,
            search_is_user_configured=False,
            retrieval_dict={},
            personal_settings_dict={},
            mcp_dict={},
            providers_dict={},
        )
        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=configs),
        ):
            label = await _resolve_agent_model_label(None)
        assert label == "openai-like/gpt-test"

    @pytest.mark.asyncio
    async def test_profile_model_takes_priority(self) -> None:
        from app.core.eval.model_config import _resolve_agent_model_label

        class FakeProfile:
            model = "anthropic/claude-sonnet-4-20250514"

        class FakeResolver:
            async def resolve(self, profile_id: str) -> FakeProfile:
                return FakeProfile()

        with patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=FakeResolver(),
        ):
            label = await _resolve_agent_model_label("builder")
        assert label == "anthropic/claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_unresolvable_profile_falls_back_to_user_model_config(
        self,
    ) -> None:
        from app.core.channel_bridge.config_loader import UserConfigs
        from app.core.eval.model_config import _resolve_agent_model_label
        from app.core.types import ModelConfig

        class FakeResolver:
            async def resolve(self, profile_id: str) -> None:
                return None

        configs = UserConfigs(
            model_cfg=ModelConfig(model="deepseek/deepseek-chat", api_key="x"),
            search_cfg=None,
            search_is_user_configured=False,
            retrieval_dict={},
            personal_settings_dict={},
            mcp_dict={},
            providers_dict={},
        )
        with (
            patch(
                "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
                return_value=FakeResolver(),
            ),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new=AsyncMock(return_value=configs),
            ),
        ):
            label = await _resolve_agent_model_label("missing_profile")
        assert label == "deepseek/deepseek-chat"

    @pytest.mark.asyncio
    async def test_unknown_when_nothing_resolvable(self) -> None:
        from app.core.eval.model_config import _resolve_agent_model_label

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=SimpleNamespace(model_cfg=None)),
        ):
            label = await _resolve_agent_model_label(None)
        assert label == "unknown"


class TestResolveJudgeConfig:
    """Judge-config resolution: configured model, absent model, incomplete config."""

    @pytest.mark.asyncio
    async def test_returns_judge_from_user_model_config(self) -> None:
        from app.core.channel_bridge.config_loader import UserConfigs
        from app.core.eval.model_config import _resolve_judge_config
        from app.core.types import ModelConfig

        configs = UserConfigs(
            model_cfg=ModelConfig(
                model="deepseek/deepseek-chat",
                api_key="sk-test",
                base_url="https://example.com",
            ),
            search_cfg=None,
            search_is_user_configured=False,
            retrieval_dict={},
            personal_settings_dict={},
            mcp_dict={},
            providers_dict={},
        )
        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(return_value=configs),
        ):
            judge, label = await _resolve_judge_config()
        assert label == "deepseek/deepseek-chat"
        assert judge is not None
        assert judge.model == "deepseek/deepseek-chat"
        assert judge.api_key == "sk-test"
        assert judge.api_base == "https://example.com"

    @pytest.mark.asyncio
    async def test_returns_none_without_model(self) -> None:
        from app.core.eval.model_config import _resolve_judge_config

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(
                return_value=SimpleNamespace(model_cfg=SimpleNamespace(model=None))
            ),
        ):
            judge, label = await _resolve_judge_config()
        assert judge is None
        assert label == "none"

    @pytest.mark.asyncio
    async def test_returns_none_on_incomplete_config(self) -> None:
        from myrm_agent_harness.api.config import ConfigIncompleteError

        from app.core.eval.model_config import _resolve_judge_config

        with patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new=AsyncMock(
                side_effect=ConfigIncompleteError(
                    user_friendly_message={"en": "x"},
                    technical_details="t",
                    resolution_steps=[],
                    error_code="provider_not_configured",
                )
            ),
        ):
            judge, label = await _resolve_judge_config()
        assert judge is None
        assert label == "none"


class TestRunEvalSuite:
    @pytest.mark.asyncio
    async def test_suite_with_external_cases(self, tmp_path: Path) -> None:
        class FakeCase:
            def __init__(self) -> None:
                self.metadata: dict[str, object] = {}
                self.turns = [object()]

        class FakeResult:
            total_cases = 1
            pass_count = 1
            fail_count = 0
            error_count = 0
            skip_count = 0
            pass_rate = 1.0
            all_passed = True
            total_ms = 10
            avg_pass_rate: float | None = None

        with (
            patch(
                "app.core.eval.service._build_eval_manifest",
                new=AsyncMock(return_value=MagicMock(to_dict=lambda: {"x": 1})),
            ),
            patch(
                "app.core.eval.executor.LocalEvalExecutor", return_value=MagicMock()
            ),
            patch("app.core.eval.service.EvalRunner") as mock_runner_cls,
            patch("app.core.eval.service.JsonlReporter", FakeJsonlReporter),
        ):
            mock_runner = MagicMock()
            mock_runner.run_multi_turn = AsyncMock(return_value=FakeResult())
            mock_runner_cls.return_value = mock_runner

            reports_dir = tmp_path / "reports"
            summary = await run_eval_suite(
                dataset_id="wb-bench-code",
                reports_dir=reports_dir,
                external_cases=[FakeCase()],
            )

        assert summary["total_cases"] == 1
        assert summary["pass_rate"] == 1.0
        assert summary["all_passed"] is True
        assert "avg_pass_rate" not in summary
        assert (reports_dir / "latest.jsonl").exists()

    @pytest.mark.asyncio
    async def test_suite_loads_cases_from_dataset_file(self, tmp_path: Path) -> None:
        class FakeCase:
            def __init__(self, profile: str) -> None:
                self.metadata = {"profile_id": profile}
                self.turns = [object()]

        cases_path = tmp_path / "ds.jsonl"
        cases_path.write_text('{"message": "hi"}\n')

        class FakeResult:
            total_cases = 2
            pass_count = 1
            fail_count = 0
            error_count = 0
            skip_count = 0
            pass_rate = 0.5
            all_passed = False
            total_ms = 5
            avg_pass_rate: float | None = None

        with (
            patch(
                "app.core.eval.service.get_dataset_path", return_value=cases_path
            ),
            patch(
                "app.core.eval.service._build_eval_manifest",
                new=AsyncMock(return_value=MagicMock(to_dict=lambda: {"x": 1})),
            ),
            patch(
                "app.core.eval.executor.LocalEvalExecutor", return_value=MagicMock()
            ),
            patch("app.core.eval.service.EvalRunner") as mock_runner_cls,
            patch("app.core.eval.service.JsonlReporter", FakeJsonlReporter),
            patch(
                "myrm_agent_harness.eval.load_multi_turn_cases",
                return_value=[FakeCase("b"), FakeCase("a"), FakeCase("a")],
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.run_multi_turn = AsyncMock(return_value=FakeResult())
            mock_runner_cls.return_value = mock_runner

            reports_dir = tmp_path / "reports"
            summary = await run_eval_suite(dataset_id="ds", reports_dir=reports_dir)

        assert summary["pass_rate"] == 0.5
        assert summary["all_passed"] is False
        assert "avg_pass_rate" not in summary
        # Cases sorted by profile then grouped (stable): a, a, b
        grouped = mock_runner.run_multi_turn.await_args[0][0]
        assert [c.metadata["profile_id"] for c in grouped] == ["a", "a", "b"]

    @pytest.mark.asyncio
    async def test_suite_creates_dummy_cases_when_missing(self, tmp_path: Path) -> None:
        cases_path = tmp_path / "ds.jsonl"

        class FakeResult:
            total_cases = 0
            pass_count = 0
            fail_count = 0
            error_count = 0
            skip_count = 0
            pass_rate = 0.0
            all_passed = True
            total_ms = 0
            avg_pass_rate: float | None = None

        with (
            patch(
                "app.core.eval.service.get_dataset_path", return_value=cases_path
            ),
            patch(
                "app.core.eval.service._build_eval_manifest",
                new=AsyncMock(return_value=MagicMock(to_dict=lambda: {"x": 1})),
            ),
            patch(
                "app.core.eval.executor.LocalEvalExecutor", return_value=MagicMock()
            ),
            patch("app.core.eval.service.EvalRunner") as mock_runner_cls,
            patch("app.core.eval.service.JsonlReporter", FakeJsonlReporter),
            patch(
                "myrm_agent_harness.eval.load_multi_turn_cases",
                return_value=[],
            ),
        ):
            mock_runner = MagicMock()
            mock_runner.run_multi_turn = AsyncMock(return_value=FakeResult())
            mock_runner_cls.return_value = mock_runner

            await run_eval_suite(dataset_id="ds", reports_dir=tmp_path / "r")

        assert cases_path.exists()
        content = cases_path.read_text()
        assert "Hello, world!" in content


class TestBackgroundWrappers:
    @pytest.mark.asyncio
    async def test_background_records_error(self) -> None:
        with patch(
            "app.core.eval.service.run_eval_suite",
            new=AsyncMock(side_effect=RuntimeError("kaboom")),
        ):
            await run_eval_suite_background(dataset_id="ds")
        assert service_mod._eval_state["error"] == "kaboom"
        assert service_mod._eval_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_background_skips_when_already_running(self) -> None:
        service_mod._eval_state["is_running"] = True
        with patch(
            "app.core.eval.service.run_eval_suite", new=AsyncMock()
        ) as mock_suite:
            await run_eval_suite_background(dataset_id="ds")
        mock_suite.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_abort_with_active_runner(self) -> None:
        service_mod._eval_state["is_running"] = True
        runner = MagicMock()
        service_mod._active_runner = runner
        assert abort_eval() is True
        runner.abort.assert_called_once()
        assert service_mod._eval_state["error"] == "Aborted by user"

    @pytest.mark.asyncio
    async def test_abort_not_running(self) -> None:
        assert abort_eval() is False

    @pytest.mark.asyncio
    async def test_wb_bench_abort_before_eval(self) -> None:
        """Abort during the build phase stops before evaluation."""
        service_mod._eval_state.clear()
        service_mod._eval_state.update(
            {
                "is_running": True,
                "abort_requested": True,
                "stage": "downloading",
                "stage_subset_id": "code",
                "download_progress": {},
            }
        )
        with (
            patch(
                "app.core.eval.wb_bench.build_wb_bench_cases",
                new=AsyncMock(return_value=([MagicMock()], {})),
            ),
            patch("app.core.eval.service.run_eval_suite", new=AsyncMock()) as mock_run,
        ):
            await run_wb_bench_background("code")
        mock_run.assert_not_awaited()
        assert service_mod._eval_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_wb_bench_download_abort_quiet(self) -> None:
        """Abort during download logs info and does not surface an error."""
        service_mod._eval_state.clear()
        service_mod._eval_state.update(
            {
                "is_running": True,
                "abort_requested": True,
                "stage": "downloading",
                "stage_subset_id": "code",
                "download_progress": {},
            }
        )
        with (
            patch(
                "app.core.eval.wb_bench.ensure_wb_bench_source",
                new=AsyncMock(
                    side_effect=RuntimeError("DownloadAbortedError")
                ),
            ),
            patch("app.core.eval.service.logger.info") as mock_info,
        ):
            await run_wb_bench_download_background("code")
        mock_info.assert_called()
        assert service_mod._eval_state.get("error") is None
        assert service_mod._eval_state["is_running"] is False

    @pytest.mark.asyncio
    async def test_wb_bench_download_error_recorded(self) -> None:
        service_mod._eval_state.clear()
        service_mod._eval_state.update(
            {
                "is_running": True,
                "abort_requested": False,
                "stage": "downloading",
                "stage_subset_id": "code",
                "download_progress": {},
            }
        )
        with patch(
            "app.core.eval.wb_bench.ensure_wb_bench_source",
            new=AsyncMock(side_effect=RuntimeError("network down")),
        ):
            await run_wb_bench_download_background("code")
        assert service_mod._eval_state["error"] == "network down"
        assert service_mod._eval_state["is_running"] is False
