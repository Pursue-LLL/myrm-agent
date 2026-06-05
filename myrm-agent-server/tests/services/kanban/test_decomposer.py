"""Unit tests for PlatformTaskDecomposer.

Mirrors the pattern of test_specifier.py: mock LiteLLM responses, verify
all outcome fields and edge-case handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban.decomposer import PlatformTaskDecomposer, _normalize_assignee


def _make_triage_task(
    title: str = "Build new cache layer",
    description: str = "",
    agent_id: str | None = None,
) -> KanbanTask:
    return KanbanTask(
        task_id="test-task-1",
        board_id="board-1",
        title=title,
        description=description,
        status=TaskStatus.TRIAGE,
        agent_id=agent_id,
    )


def _make_llm_response(
    content: str,
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    resp.usage = usage
    return resp


ROSTER = [{"name": "coder", "description": "Writes code"}, {"name": "reviewer", "description": "Reviews code"}]


class TestNormalizeAssignee:
    def test_valid_assignee(self) -> None:
        assert (
            _normalize_assignee(
                "coder",
                default_assignee="default",
                valid_names={"coder", "reviewer"},
            )
            == "coder"
        )

    def test_invalid_assignee_falls_back(self) -> None:
        assert (
            _normalize_assignee(
                "unknown",
                default_assignee="default",
                valid_names={"coder"},
            )
            == "default"
        )

    def test_empty_string_falls_back(self) -> None:
        assert (
            _normalize_assignee(
                "",
                default_assignee="default",
                valid_names={"coder"},
            )
            == "default"
        )

    def test_none_falls_back(self) -> None:
        assert (
            _normalize_assignee(
                None,
                default_assignee="default",
                valid_names={"coder"},
            )
            == "default"
        )

    def test_whitespace_stripped(self) -> None:
        assert (
            _normalize_assignee(
                "  coder  ",
                default_assignee="default",
                valid_names={"coder"},
            )
            == "coder"
        )


@pytest.mark.asyncio
async def test_rejects_non_triage_task() -> None:
    d = PlatformTaskDecomposer()
    task = KanbanTask(
        task_id="t1",
        board_id="b1",
        title="x",
        status=TaskStatus.READY,
    )
    outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")
    assert not outcome.ok
    assert outcome.reason == "not_triage"


@pytest.mark.asyncio
async def test_unavailable_when_kwargs_fail() -> None:
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    with patch(
        "app.services.agent.platform_config.build_platform_litellm_kwargs",
        new_callable=AsyncMock,
        side_effect=RuntimeError("no config"),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")
    assert not outcome.ok
    assert outcome.reason == "decomposer_unavailable"


@pytest.mark.asyncio
async def test_fanout_true_parses_children() -> None:
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    content = '{"fanout": true, "rationale": "split", "tasks": [{"title": "T1", "body": "B1", "assignee": "coder", "parents": []}, {"title": "T2", "body": "B2", "assignee": "reviewer", "parents": [0]}]}'
    llm_resp = _make_llm_response(content)
    with (
        patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new_callable=AsyncMock,
            return_value={"model": "gpt-4o"},
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")

    assert outcome.ok
    assert outcome.fanout
    assert len(outcome.children) == 2
    assert outcome.children[0].title == "T1"
    assert outcome.children[0].assignee == "coder"
    assert outcome.children[1].parent_indices == (0,)
    assert outcome.prompt_tokens == 100


@pytest.mark.asyncio
async def test_fanout_false_returns_spec() -> None:
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    content = (
        '{"fanout": false, "rationale": "single task", "title": "Refined title", "body": "Detailed body", "assignee": "coder"}'
    )
    llm_resp = _make_llm_response(content)
    with (
        patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new_callable=AsyncMock,
            return_value={"model": "gpt-4o"},
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")

    assert outcome.ok
    assert not outcome.fanout
    assert outcome.reason == "no_fanout"
    assert outcome.new_title == "Refined title"
    assert outcome.new_body == "Detailed body"
    assert outcome.new_assignee == "coder"


@pytest.mark.asyncio
async def test_fanout_false_empty_title_body_returns_not_ok() -> None:
    """When fanout=false but LLM returns no title and no body, should fail."""
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    content = '{"fanout": false, "rationale": "cannot decompose"}'
    llm_resp = _make_llm_response(content)
    with (
        patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new_callable=AsyncMock,
            return_value={"model": "gpt-4o"},
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")

    assert not outcome.ok
    assert outcome.reason == "no_fanout_empty_result"
    assert outcome.prompt_tokens == 100


@pytest.mark.asyncio
async def test_fanout_false_invalid_assignee_falls_back() -> None:
    """When fanout=false and LLM picks an unknown assignee, it normalizes to default."""
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    content = '{"fanout": false, "rationale": "ok", "title": "T", "body": "B", "assignee": "nonexistent"}'
    llm_resp = _make_llm_response(content)
    with (
        patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new_callable=AsyncMock,
            return_value={"model": "gpt-4o"},
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")

    assert outcome.ok
    assert outcome.new_assignee == "default"


@pytest.mark.asyncio
async def test_malformed_json_returns_parse_failed() -> None:
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    llm_resp = _make_llm_response("This is plain text, no JSON.")
    with (
        patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new_callable=AsyncMock,
            return_value={"model": "gpt-4o"},
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")

    assert not outcome.ok
    assert outcome.reason == "parse_failed"


@pytest.mark.asyncio
async def test_empty_tasks_list_returns_not_ok() -> None:
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    content = '{"fanout": true, "rationale": "split", "tasks": []}'
    llm_resp = _make_llm_response(content)
    with (
        patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new_callable=AsyncMock,
            return_value={"model": "gpt-4o"},
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")

    assert not outcome.ok
    assert outcome.reason == "empty_tasks_list"


@pytest.mark.asyncio
async def test_llm_error_returns_not_ok() -> None:
    d = PlatformTaskDecomposer()
    task = _make_triage_task()
    with (
        patch(
            "app.services.agent.platform_config.build_platform_litellm_kwargs",
            new_callable=AsyncMock,
            return_value={"model": "gpt-4o"},
        ),
        patch("litellm.acompletion", new_callable=AsyncMock, side_effect=ConnectionError("fail")),
    ):
        outcome = await d.decompose(task, roster=ROSTER, default_assignee="default")

    assert not outcome.ok
    assert "llm_error" in outcome.reason
