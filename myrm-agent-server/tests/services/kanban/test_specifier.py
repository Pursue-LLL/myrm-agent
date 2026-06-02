"""Unit tests for PlatformTaskSpecifier."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban.llm_utils import extract_json_blob, has_cjk, truncate
from app.services.kanban.specifier import PlatformTaskSpecifier

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


def _make_llm_response(content: str, prompt_tokens: int = 100, completion_tokens: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp.usage = usage
    return resp


@pytest.mark.asyncio
async def test_specify_rejects_non_triage_task() -> None:
    specifier = PlatformTaskSpecifier()
    task = KanbanTask(
        task_id="t1", board_id="b1", title="x", status=TaskStatus.READY,
    )
    outcome = await specifier.specify(task)
    assert not outcome.ok
    assert outcome.reason == "not_triage"


@pytest.mark.asyncio
async def test_specify_returns_unavailable_when_kwargs_fail() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
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
    llm_resp = _make_llm_response(
        '{"title": "Implement dark mode toggle", "body": "**Goal** Dark mode support"}',
    )
    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4o"},
    ), patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp):
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
    llm_resp = _make_llm_response("This is just plain text, no JSON here.")
    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4o"},
    ), patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp):
        outcome = await specifier.specify(task)

    assert outcome.ok
    assert outcome.reason == "parse_failed_fallback"
    assert outcome.new_title is None
    assert outcome.new_body == "This is just plain text, no JSON here."


@pytest.mark.asyncio
async def test_specify_returns_empty_response() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    llm_resp = _make_llm_response("")
    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4o"},
    ), patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp):
        outcome = await specifier.specify(task)

    assert not outcome.ok
    assert outcome.reason == "empty_response"


@pytest.mark.asyncio
async def test_specify_handles_llm_exception() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4o"},
    ), patch("litellm.acompletion", new_callable=AsyncMock, side_effect=TimeoutError("timeout")):
        outcome = await specifier.specify(task)

    assert not outcome.ok
    assert "llm_error" in outcome.reason
    assert "TimeoutError" in outcome.reason


@pytest.mark.asyncio
async def test_specify_picks_cjk_prompt_for_chinese_title() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task(title="给项目加个暗黑模式")
    llm_resp = _make_llm_response('{"title": "实现暗黑模式切换", "body": "**Goal** 支持暗黑模式"}')

    captured_messages: list[dict[str, str]] = []

    async def mock_acompletion(**kwargs: object) -> MagicMock:
        captured_messages.extend(kwargs.get("messages", []))  # type: ignore[arg-type]
        return llm_resp

    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4o"},
    ), patch("litellm.acompletion", side_effect=mock_acompletion):
        outcome = await specifier.specify(task)

    assert outcome.ok
    assert any("看板任务规范化助手" in str(m.get("content", "")) for m in captured_messages)


@pytest.mark.asyncio
async def test_specify_picks_english_prompt_for_english_title() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task(title="Add dark mode toggle")
    llm_resp = _make_llm_response('{"title": "Implement dark mode", "body": "**Goal** ..."}')

    captured_messages: list[dict[str, str]] = []

    async def mock_acompletion(**kwargs: object) -> MagicMock:
        captured_messages.extend(kwargs.get("messages", []))  # type: ignore[arg-type]
        return llm_resp

    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4o"},
    ), patch("litellm.acompletion", side_effect=mock_acompletion):
        outcome = await specifier.specify(task)

    assert outcome.ok
    assert any("Kanban triage specifier" in str(m.get("content", "")) for m in captured_messages)


@pytest.mark.asyncio
async def test_specify_missing_title_and_body() -> None:
    specifier = PlatformTaskSpecifier()
    task = _make_triage_task()
    llm_resp = _make_llm_response('{"foo": "bar"}')
    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        return_value={"model": "gpt-4o"},
    ), patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp):
        outcome = await specifier.specify(task)

    assert not outcome.ok
    assert outcome.reason == "missing_title_and_body"
