"""Unit tests for MCP E2E stream print helpers."""

from tests.api.agent.mcp_e2e_stream import print_tasks_steps_payload


def test_print_tasks_steps_payload_file_read(capsys) -> None:
    print_tasks_steps_payload(
        "file_read_tool",
        [{"file_path": "/mcp/mcp_12306_skill/get_tickets.md"}],
    )
    out = capsys.readouterr().out
    assert "file_path=/mcp/mcp_12306_skill/get_tickets.md" in out


def test_print_tasks_steps_payload_bash_truncates_long_code(capsys) -> None:
    long_code = "x" * 3500
    print_tasks_steps_payload("bash_code_execute_tool", [{"code": long_code}])
    out = capsys.readouterr().out
    assert "code (3500 chars)" in out
    assert "[truncated]" in out
    assert long_code not in out


def test_print_tasks_steps_payload_skill_select(capsys) -> None:
    print_tasks_steps_payload("skill_select_tool", [{"skill_name": "mcp_12306_skill"}])
    out = capsys.readouterr().out
    assert "skill_name=mcp_12306_skill" in out


def test_print_tasks_steps_payload_ignores_non_list() -> None:
    print_tasks_steps_payload("file_read_tool", "not-a-list")
