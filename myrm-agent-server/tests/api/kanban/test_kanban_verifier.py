"""Tests for KanbanCompletionVerifier (hallucination gate).

Covers: JSON parsing, normalization, verification flow with mocked LLM,
pass-through for tasks without criteria, error handling.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.core.kanban.verifier import (
    KanbanCompletionVerifier,
    _parse_criteria,
    _trim_result_for_judge,
)
from app.core.utils.chat_utils import parse_judge_json

# --------------- parse_judge_json tests ---------------


class TestParseJudgeJson:
    def test_valid_json_directly(self) -> None:
        result = parse_judge_json('{"done": true, "reason": "all good"}')
        assert result is not None
        assert result["done"] is True
        assert result["reason"] == "all good"

    def test_json_in_code_block(self) -> None:
        raw = '```json\n{"done": false, "reason": "missing step"}\n```'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is False

    def test_json_in_bare_code_block(self) -> None:
        raw = '```\n{"done": true, "reason": "ok"}\n```'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is True

    def test_inline_json_extraction(self) -> None:
        raw = 'Analysis: {"done": false, "reason": "incomplete"} extra text'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is False
        assert result["reason"] == "incomplete"

    def test_no_json_returns_none(self) -> None:
        assert parse_judge_json("no json here") is None

    def test_json_without_done_key_returns_none(self) -> None:
        assert parse_judge_json('{"result": true}') is None

    def test_unquoted_keys_repaired(self) -> None:
        """无引号 key 由 json_repair 兜底修复（框架 utils.json_parsing 容错能力）。"""
        result = parse_judge_json('{done: true, reason: "ok"}')
        assert result is not None
        assert result["done"] is True
        assert result["reason"] == "ok"

    def test_hopeless_garbage_returns_none(self) -> None:
        assert parse_judge_json("{done: ") is None

    def test_unescaped_newline_in_reasoning(self) -> None:
        raw = '{"done": true, "reason": "verified\\nby inspection"}'
        result = parse_judge_json(raw)
        assert result is not None
        assert result["done"] is True


class TestNormalizeDone:
    def test_bool_passthrough(self) -> None:
        obj = '{"done": true, "reason": "x"}'
        assert parse_judge_json(obj)["done"] is True

    def test_string_true_variations(self) -> None:
        for val in ("true", "True", "TRUE", "yes", "Yes", "1"):
            raw = f'{{"done": "{val}", "reason": "r"}}'
            assert parse_judge_json(raw)["done"] is True, f"Failed for {val!r}"

    def test_string_false_variations(self) -> None:
        for val in ("false", "no", "0", "nope"):
            raw = f'{{"done": "{val}", "reason": "r"}}'
            assert parse_judge_json(raw)["done"] is False, f"Failed for {val!r}"


# --------------- KanbanCompletionVerifier tests ---------------


def _make_task(
    criteria: str | list[dict[str, str | int]] | None = None,
    title: str = "Test task",
    description: str = "",
) -> KanbanTask:
    metadata: dict[str, object] = {}
    if criteria is not None:
        metadata["completion_criteria"] = criteria
    return KanbanTask(
        task_id="test123",
        board_id="board1",
        title=title,
        description=description,
        status=TaskStatus.RUNNING,
        metadata=metadata,
    )


def _mock_llm_response(content: str) -> SimpleNamespace:
    """Build a mock LLM response matching litellm's response shape."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


class TestKanbanCompletionVerifier:
    @pytest.mark.asyncio
    async def test_no_criteria_passes_through(self) -> None:
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria=None), "done")
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_empty_string_criteria_passes_through(self) -> None:
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="  "), "done")
        assert result.passed is True

    def test_list_string_criteria_parsed_as_semantic(self) -> None:
        shell_configs, semantic_texts = _parse_criteria(["step A done", "step B done"])
        assert shell_configs == []
        assert semantic_texts == ["step A done", "step B done"]

    def test_structured_criteria_parsed(self) -> None:
        raw = [
            {"type": "shell", "command": "test -f /output.csv"},
            {"type": "semantic", "criteria": "report is complete"},
        ]
        shell_configs, semantic_texts = _parse_criteria(raw)
        assert len(shell_configs) == 1
        assert shell_configs[0]["command"] == "test -f /output.csv"
        assert semantic_texts == ["report is complete"]

    def test_plain_string_criteria_parsed(self) -> None:
        shell_configs, semantic_texts = _parse_criteria("must pass all tests")
        assert shell_configs == []
        assert semantic_texts == ["must pass all tests"]

    def test_empty_criteria_parsed(self) -> None:
        shell_configs, semantic_texts = _parse_criteria("")
        assert shell_configs == []
        assert semantic_texts == []

    def test_none_criteria_parsed(self) -> None:
        shell_configs, semantic_texts = _parse_criteria(None)
        assert shell_configs == []
        assert semantic_texts == []

    def test_invalid_type_ignored(self) -> None:
        raw = [{"type": "unknown", "command": "echo hi"}]
        shell_configs, semantic_texts = _parse_criteria(raw)
        assert shell_configs == []
        assert semantic_texts == []

    def test_empty_command_shell_ignored(self) -> None:
        raw = [{"type": "shell", "command": ""}]
        shell_configs, semantic_texts = _parse_criteria(raw)
        assert shell_configs == []

    def test_mixed_valid_and_invalid_items(self) -> None:
        raw = [
            {"type": "shell", "command": "ls"},
            {"type": "invalid"},
            42,
            {"type": "semantic", "criteria": "ok"},
            {"type": "shell", "command": "  "},
        ]
        shell_configs, semantic_texts = _parse_criteria(raw)
        assert len(shell_configs) == 1
        assert shell_configs[0]["command"] == "ls"
        assert semantic_texts == ["ok"]

    def test_empty_list_criteria(self) -> None:
        shell_configs, semantic_texts = _parse_criteria([])
        assert shell_configs == []
        assert semantic_texts == []

    def test_whitespace_only_string_criteria(self) -> None:
        shell_configs, semantic_texts = _parse_criteria("   \n\t  ")
        assert shell_configs == []
        assert semantic_texts == []

    def test_semantic_with_empty_criteria_ignored(self) -> None:
        raw = [{"type": "semantic", "criteria": ""}]
        shell_configs, semantic_texts = _parse_criteria(raw)
        assert semantic_texts == []

    @pytest.mark.asyncio
    @patch("app.core.kanban.verifier.ShellCriterion")
    async def test_shell_timeout_non_numeric_defaults_to_60(
        self, mock_shell_cls: AsyncMock
    ) -> None:
        from myrm_agent_harness.agent.goals.verification.base import (
            VerificationResult as VR,
        )

        mock_instance = AsyncMock()
        mock_instance.verify.return_value = VR(passed=True)
        mock_shell_cls.return_value = mock_instance

        task = _make_task()
        task.metadata["completion_criteria"] = [
            {"type": "shell", "command": "echo ok", "timeout_seconds": "not_a_number"},
        ]
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(task, "done")
        assert result.passed is True
        mock_shell_cls.assert_called_once_with(command="echo ok", timeout_seconds=60)

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_empty_response_no_reasoning_fails(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""))],
        )
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="check"), "done")
        assert result.passed is False

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_judge_returns_done_true(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = _mock_llm_response(
            '{"done": true, "reason": "All criteria met"}',
        )
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(
            _make_task(criteria="Must pass tests"), "All tests passed"
        )
        assert result.passed is True
        assert "All criteria met" in (result.reason or "")

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_judge_returns_done_false(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = _mock_llm_response(
            '{"done": false, "reason": "Tests not run"}',
        )
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(
            _make_task(criteria="Run all tests"), "I wrote the code"
        )
        assert result.passed is False
        assert "Tests not run" in (result.reason or "")

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_judge_returns_json_in_code_block(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = _mock_llm_response(
            '```json\n{"done": true, "reason": "confirmed"}\n```',
        )
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="Done"), "result")
        assert result.passed is True

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_judge_returns_unparseable_with_pass(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = _mock_llm_response("PASS - looks good to me")
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="check"), "done")
        assert result.passed is True

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_judge_returns_unparseable_text_fails(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = _mock_llm_response("The task is not complete.")
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="check"), "done")
        assert result.passed is False

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_llm_exception_returns_failure(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.side_effect = RuntimeError("API unavailable")
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="check"), "done")
        assert result.passed is False
        assert result.error_logs is not None
        assert "API unavailable" in result.error_logs

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_judge_empty_response_uses_reasoning(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="",
                        reasoning_content='{"done": true, "reason": "ok from reasoning"}',
                    ),
                )
            ],
        )
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="check"), "done")
        assert result.passed is True

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_judge_done_string_normalized(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = _mock_llm_response(
            '{"done": "True", "reason": "string bool"}',
        )
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(_make_task(criteria="check"), "done")
        assert result.passed is True

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    async def test_result_truncated_to_3000_chars(
        self, mock_llm: AsyncMock, _mock_cfg: AsyncMock
    ) -> None:
        mock_llm.return_value = _mock_llm_response('{"done": true, "reason": "ok"}')
        verifier = KanbanCompletionVerifier()
        long_result = "x" * 5000
        await verifier.verify(_make_task(criteria="check"), long_result)

        call_args = mock_llm.call_args
        user_msg = call_args.kwargs["messages"][1]["content"]
        assert len(user_msg) < 3100

    @pytest.mark.asyncio
    @patch(
        "app.core.kanban.verifier.ShellCriterion",
    )
    async def test_shell_criteria_failure_skips_llm(
        self, mock_shell_cls: AsyncMock
    ) -> None:
        from myrm_agent_harness.agent.goals.verification.base import VerificationResult

        mock_instance = AsyncMock()
        mock_instance.verify.return_value = VerificationResult(
            passed=False,
            reason="file not found",
            error_logs="exit code 1",
        )
        mock_shell_cls.return_value = mock_instance

        task = _make_task()
        task.metadata["completion_criteria"] = [
            {"type": "shell", "command": "test -f /missing.csv"},
            {"type": "semantic", "criteria": "data is complete"},
        ]
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(task, "done")
        assert result.passed is False
        assert "Shell verification failed" in (result.reason or "")

    @pytest.mark.asyncio
    @patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={},
    )
    @patch("litellm.acompletion", new_callable=AsyncMock)
    @patch("app.core.kanban.verifier.ShellCriterion")
    async def test_shell_pass_then_semantic(
        self,
        mock_shell_cls: AsyncMock,
        mock_llm: AsyncMock,
        _mock_cfg: AsyncMock,
    ) -> None:
        from myrm_agent_harness.agent.goals.verification.base import (
            VerificationResult as VR,
        )

        mock_instance = AsyncMock()
        mock_instance.verify.return_value = VR(passed=True)
        mock_shell_cls.return_value = mock_instance

        mock_llm.return_value = _mock_llm_response(
            '{"done": true, "reason": "all good"}'
        )

        task = _make_task()
        task.metadata["completion_criteria"] = [
            {"type": "shell", "command": "test -f /output.csv"},
            {"type": "semantic", "criteria": "report is complete"},
        ]
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(task, "done")
        assert result.passed is True
        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.core.kanban.verifier.ShellCriterion")
    async def test_shell_only_criteria_passes(self, mock_shell_cls: AsyncMock) -> None:
        from myrm_agent_harness.agent.goals.verification.base import (
            VerificationResult as VR,
        )

        mock_instance = AsyncMock()
        mock_instance.verify.return_value = VR(passed=True)
        mock_shell_cls.return_value = mock_instance

        task = _make_task()
        task.metadata["completion_criteria"] = [
            {"type": "shell", "command": "test -f /output.csv"},
        ]
        verifier = KanbanCompletionVerifier()
        result = await verifier.verify(task, "done")
        assert result.passed is True


# --------------- _trim_result_for_judge tests ---------------


class TestTrimResultForJudge:
    def test_short_result_passthrough(self) -> None:
        assert _trim_result_for_judge("short") == "short"
        assert _trim_result_for_judge("x" * 3000) == "x" * 3000

    def test_long_result_keeps_head_and_tail(self) -> None:
        long = "A" * 2200 + "B" * 1200
        trimmed = _trim_result_for_judge(long)
        assert trimmed.startswith("A" * 2000)
        assert trimmed.endswith("B" * 1000)
        assert "[truncated" in trimmed

    def test_long_result_marks_omitted_count(self) -> None:
        long = "x" * 4000
        trimmed = _trim_result_for_judge(long)
        assert "[truncated 1000 chars]" in trimmed

    def test_empty_result(self) -> None:
        assert _trim_result_for_judge("") == ""
