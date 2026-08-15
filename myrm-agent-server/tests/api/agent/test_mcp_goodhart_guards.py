"""Unit tests for 12306 MCP E2E Goodhart guard helpers."""

import pytest

from tests.api.agent.mcp_e2e_goodhart import (
    answer_looks_like_ticket_result,
    assert_12306_ticket_evidence_delivered,
    mcp_bash_get_tickets_succeeded,
    mcp_get_tickets_delivered,
    mcp_no_skill_usage_memory_search,
    mcp_ptc_get_tickets_engaged,
)


def _tasks_step(
    tool_name: str, data: list[dict[str, object]], *, status: str | None = None
) -> dict[str, object]:
    event: dict[str, object] = {
        "type": "tasks_steps",
        "tool_name": tool_name,
        "data": data,
    }
    if status is not None:
        event["status"] = status
    return event


def test_get_tickets_engaged_via_file_read() -> None:
    collected = [
        _tasks_step(
            "file_read_tool",
            [{"file_path": "/mcp/mcp_12306_skill/get_tickets.md"}],
        )
    ]
    assert mcp_ptc_get_tickets_engaged(collected, "12306") is True


def test_get_tickets_engaged_via_bash_import() -> None:
    collected = [
        _tasks_step(
            "bash_code_execute_tool",
            [
                {
                    "code": "from skills.mcp_12306_skill import get_tickets\nprint(get_tickets(...))"
                }
            ],
        )
    ]
    assert mcp_ptc_get_tickets_engaged(collected, "12306") is True


def test_get_tickets_not_engaged_when_only_station_lookup() -> None:
    collected = [
        _tasks_step(
            "file_read_tool",
            [{"file_path": "/mcp/mcp_12306_skill/get_station_code_of_citys.md"}],
        ),
        _tasks_step(
            "bash_code_execute_tool",
            [
                {
                    "code": "from skills.mcp_12306_skill import get_current_date, get_station_code_of_citys"
                }
            ],
        ),
    ]
    assert mcp_ptc_get_tickets_engaged(collected, "12306") is False


def test_no_skill_usage_memory_search_passes_without_memory_search() -> None:
    collected = [
        _tasks_step("skill_select_tool", [{"skill_name": "mcp_12306_skill"}]),
        _tasks_step(
            "file_read_tool",
            [{"file_path": "/mcp/mcp_12306_skill/get_tickets.md"}],
        ),
        _tasks_step(
            "bash_code_execute_tool",
            [{"code": "from skills.mcp_12306_skill import get_tickets"}],
        ),
    ]
    assert mcp_no_skill_usage_memory_search(collected, "12306") is True


def test_no_skill_usage_memory_search_fails_on_usage_lookup() -> None:
    collected = [
        _tasks_step("skill_select_tool", [{"skill_name": "mcp_12306_skill"}]),
        _tasks_step(
            "memory_search_tool",
            [{"query": "how to use the 12306 skill"}],
        ),
    ]
    assert mcp_no_skill_usage_memory_search(collected, "12306") is False


def test_no_skill_usage_memory_search_ignores_unrelated_query() -> None:
    collected = [
        _tasks_step(
            "memory_search_tool",
            [{"query": "user's travel preferences"}],
        ),
        _tasks_step("skill_select_tool", [{"skill_name": "mcp_12306_skill"}]),
    ]
    assert mcp_no_skill_usage_memory_search(collected, "12306") is True


def test_bash_get_tickets_succeeded_requires_success_status() -> None:
    collected = [
        _tasks_step(
            "bash_code_execute_tool",
            [{"code": "from skills.mcp_12306_skill import get_tickets"}],
            status="error",
        )
    ]
    assert mcp_bash_get_tickets_succeeded(collected, "12306") is False

    collected.append(
        _tasks_step(
            "bash_code_execute_tool",
            [{"code": "from skills.mcp_12306_skill import get_tickets"}],
            status="success",
        )
    )
    assert mcp_bash_get_tickets_succeeded(collected, "12306") is True


def test_answer_ticket_heuristic_accepts_train_listing() -> None:
    answer = (
        "北京南 -> 上海虹桥 高铁前5趟：\n"
        "1. G1 出发 09:00 到达 13:28 历时 4小时28分\n"
        "2. G3 出发 09:30 到达 14:00 历时 4小时30分\n"
        "3. G5 出发 10:00 到达 14:30 历时 4小时30分\n"
    )
    assert answer_looks_like_ticket_result(answer) is True


def test_answer_ticket_heuristic_rejects_iteration_limit_boilerplate() -> None:
    answer = (
        "I reached the iteration limit before completing the task. "
        "Please resume or ask again with a narrower request."
    )
    assert answer_looks_like_ticket_result(answer) is False


def test_answer_ticket_heuristic_accepts_summary_after_iteration_limit_suffix() -> None:
    answer = (
        "查询已完成，前 5 趟高铁车次信息已在上方表格中呈现。"
        "I reached the iteration limit before completing the task."
    )
    assert answer_looks_like_ticket_result(answer) is True


def test_mcp_get_tickets_delivered_detects_mcp_metadata() -> None:
    collected = [
        {
            "type": "tasks_steps",
            "tool_name": "unknown",
            "data": [
                {
                    "type": "mcp",
                    "skill_name": "mcp_12306_skill",
                    "calls": [
                        {
                            "tool_name": "get-tickets",
                            "result_preview": "G531 北京南 -> 上海虹桥 06:08 -> 12:04",
                        }
                    ],
                }
            ],
        }
    ]
    assert mcp_get_tickets_delivered(collected, "12306") is True


def test_answer_ticket_heuristic_rejects_short_reply() -> None:
    assert answer_looks_like_ticket_result("查询完成。") is False


def test_assert_ticket_evidence_passes_on_mcp_deliver() -> None:
    collected = [
        {
            "type": "tasks_steps",
            "tool_name": "unknown",
            "data": [
                {
                    "type": "mcp",
                    "skill_name": "mcp_12306_skill",
                    "calls": [
                        {
                            "tool_name": "get-tickets",
                            "result_preview": "G531 北京南 -> 上海虹桥",
                        }
                    ],
                }
            ],
        }
    ]
    assert_12306_ticket_evidence_delivered(collected, "无关回答")


def test_assert_ticket_evidence_rejects_answer_only_goodhart() -> None:
    collected: list[dict[str, object]] = []
    answer = "G1 北京南 09:00 上海虹桥 13:28 高铁车次查询完成"
    with pytest.raises(AssertionError, match="did not deliver MCP get-tickets metadata"):
        assert_12306_ticket_evidence_delivered(collected, answer)
