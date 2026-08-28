"""Unit tests for PlatformTaskSpecifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban.llm_utils import extract_json_blob, has_cjk, truncate
from app.services.kanban.specify import PlatformTaskSpecifier

# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_string_unchanged(self) -> None:
        assert truncate("hello", 10) == "hello"

    def test_exact_limit_unchanged(self) -> None:
        assert truncate("12345", 5) == "12345"

    def test_over_limittruncated(self) -> None:
        result = truncate("abcdef", 5)
        assert len(result) == 5
        assert result.endswith("\u2026")


class TestExtractLangchainUsage:
    def test_reads_token_usage_metadata(self) -> None:
        from app.services.kanban.llm_utils import extract_langchain_usage

        message = MagicMock()
        message.response_metadata = {
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }
        assert extract_langchain_usage(message) == (10, 20)

    def test_reads_openai_style_usage_keys(self) -> None:
        from app.services.kanban.llm_utils import extract_langchain_usage

        message = MagicMock()
        message.response_metadata = {
            "usage": {"input_tokens": 5, "output_tokens": 7},
        }
        assert extract_langchain_usage(message) == (5, 7)


class TestHasCjk:
    def test_english_only(self) -> None:
        assert has_cjk("Add a dark mode toggle") is False

    def test_chinese_characters(self) -> None:
        assert has_cjk("给项目加个暗黑模式") is True

    def test_japanese_hiragana(self) -> None:
        assert has_cjk("メールの自動返信") is True

    def test_mixed_with_cjk(self) -> None:
        assert has_cjk("fix bug 修复问题") is True


class TestExtractJsonBlob:
    def test_plain_json(self) -> None:
        raw = '{"title": "T", "body": "B"}'
        assert extract_json_blob(raw) == {"title": "T", "body": "B"}

    def test_fenced_json(self) -> None:
        raw = '```json\n{"title": "T", "body": "B"}\n```'
        assert extract_json_blob(raw) == {"title": "T", "body": "B"}

    def test_prose_preamble(self) -> None:
        raw = 'Sure! Here you go:\n{"title": "T", "body": "B"}\nThanks.'
        assert extract_json_blob(raw) == {"title": "T", "body": "B"}

    def test_empty_string(self) -> None:
        assert extract_json_blob("") is None

    def test_no_json(self) -> None:
        assert extract_json_blob("no json here") is None

    def test_non_dict_json(self) -> None:
        assert extract_json_blob("[1, 2, 3]") is None

    def test_unescaped_newline_in_string(self) -> None:
        """推理模型在字符串字面量内输出裸换行时应容错提取。"""
        raw = '{"title": "line one\nline two", "body": "B"}'
        assert extract_json_blob(raw) == {"title": "line one\nline two", "body": "B"}

    def test_multiple_objects_picks_last(self) -> None:
        """格式示例对象在前、真实结果在后时应取真实结果（最后者）。"""
        raw = '```json\n{"title": "example", "body": "demo"}\n```\nreal spec:\n{"title": "T", "body": "B"}'
        assert extract_json_blob(raw) == {"title": "T", "body": "B"}


# ---------------------------------------------------------------------------
# PlatformTaskSpecifier tests
# ---------------------------------------------------------------------------


def _make_triage_task(
    title: str = "Add dark mode",
    description: str = "",
) -> KanbanTask:
    return KanbanTask(
        task_id="test-task-1",
        board_id="board-1",
        title=title,
        description=description,
        status=TaskStatus.TRIAGE,
    )


def _mock_platform_llm(
    content: str,
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
) -> MagicMock:
    llm = MagicMock()
    response = MagicMock()
    response.content = content
    response.response_metadata = {
        "token_usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
    }
    llm.ainvoke = AsyncMock(return_value=response)
    return llm


@pytest.mark.asyncio
async def test_specify_rejects_non_triage_task() -> None:
    specifier = PlatformTaskSpecifier()
    task = KanbanTask(
        task_id="t1",
        board_id="b1",
        title="x",
        status=TaskStatus.READY,
    )
    outcome = await specifier.specify(task)
    assert not outcome.ok
    assert outcome.reason == "not_triage"


@pytest.mark.asyncio
async def test_specify_returns_unavailable_when_kwargs_fail() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no config"),
    ):
        outcome = await specifier.specify(task)
    assert not outcome.ok
    assert outcome.reason == "specifier_unavailable"


@pytest.mark.asyncio
async def test_specify_parses_valid_json_response() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    content = '{"title": "Implement dark mode toggle", "body": "**Goal** Dark mode support"}'
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        return_value=_mock_platform_llm(content),
    ):
        outcome = await specifier.specify(task)

    assert outcome.ok
    assert outcome.new_title == "Implement dark mode toggle"
    assert outcome.new_body == "**Goal** Dark mode support"
    assert outcome.prompt_tokens == 100
    assert outcome.completion_tokens == 200
    assert not outcome.persisted


@pytest.mark.asyncio
async def test_specify_fallback_when_json_parse_fails() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    plain = "This is just plain text, no JSON here."
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        return_value=_mock_platform_llm(plain),
    ):
        outcome = await specifier.specify(task)

    assert outcome.ok
    assert outcome.reason == "parse_failed_fallback"
    assert outcome.new_title is None
    assert outcome.new_body == plain


@pytest.mark.asyncio
async def test_specify_returns_empty_response() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        return_value=_mock_platform_llm(""),
    ):
        outcome = await specifier.specify(task)

    assert not outcome.ok
    assert outcome.reason == "empty_response"


@pytest.mark.asyncio
async def test_specify_handles_llm_exception() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    failing_llm = MagicMock()
    failing_llm.ainvoke = AsyncMock(side_effect=TimeoutError("timeout"))
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        return_value=failing_llm,
    ):
        outcome = await specifier.specify(task)

    assert not outcome.ok
    assert "llm_error" in outcome.reason
    assert "TimeoutError" in outcome.reason


@pytest.mark.asyncio
async def test_specify_picks_cjk_prompt_for_chinese_title() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task(title="给项目加个暗黑模式")
    captured_messages: list[object] = []

    async def mock_ainvoke(messages: list[object], **kwargs: object) -> MagicMock:
        captured_messages.extend(messages)
        response = MagicMock()
        response.content = '{"title": "实现暗黑模式切换", "body": "**Goal** 支持暗黑模式"}'
        response.response_metadata = {"token_usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        return response

    mock_llm = MagicMock()
    mock_llm.ainvoke = mock_ainvoke
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        return_value=mock_llm,
    ):
        outcome = await specifier.specify(task)

    assert outcome.ok
    assert any("看板任务规范化助手" in str(getattr(m, "content", "")) for m in captured_messages)


@pytest.mark.asyncio
async def test_specify_picks_english_prompt_for_english_title() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task(title="Add dark mode toggle")
    captured_messages: list[object] = []

    async def mock_ainvoke(messages: list[object], **kwargs: object) -> MagicMock:
        captured_messages.extend(messages)
        response = MagicMock()
        response.content = '{"title": "Implement dark mode", "body": "**Goal** ..."}'
        response.response_metadata = {"token_usage": {"prompt_tokens": 1, "completion_tokens": 1}}
        return response

    mock_llm = MagicMock()
    mock_llm.ainvoke = mock_ainvoke
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        return_value=mock_llm,
    ):
        outcome = await specifier.specify(task)

    assert outcome.ok
    assert any("Kanban triage specifier" in str(getattr(m, "content", "")) for m in captured_messages)


@pytest.mark.asyncio
async def test_specify_missing_title_and_body() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    with patch(
        "app.services.agent.platform_config.load_platform_llm",
        new_callable=AsyncMock,
        return_value=_mock_platform_llm('{"foo": "bar"}'),
    ):
        outcome = await specifier.specify(task)

    assert not outcome.ok
    assert outcome.reason == "missing_title_and_body"
