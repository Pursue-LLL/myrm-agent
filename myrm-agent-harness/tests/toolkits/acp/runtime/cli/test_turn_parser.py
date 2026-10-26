"""``TurnParser`` over the output formats of the CLI agents: one line in, at most one event out."""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import TurnParser
from myrm_agent_harness.toolkits.acp.types import RuntimeEvent, RuntimeEventType


def _parse(line: str, session_id: str = "s1") -> RuntimeEvent | None:
    events = TurnParser(session_id).feed(line)
    assert len(events) <= 1, events
    return events[0] if events else None


class TestClaudeAndGenericFormats:
    """One line in, at most one event out, for the Claude / generic / Codex legacy formats."""

    def test_text_event(self) -> None:
        event = _parse(
            json.dumps({"type": "assistant", "content": "hello"}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert event.data["content"] == "hello"

    def test_text_event_content_list(self) -> None:
        event = _parse(
            json.dumps({"type": "assistant", "content": [{"type": "text", "text": "hi"}]}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert event.data["content"] == "hi"

    def test_nested_message_content(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"content": [{"type": "text", "text": "nested"}]},
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert event.data["content"] == "nested"

    def test_tool_use_event(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "tool_use",
                    "name": "bash",
                    "input": {"cmd": "ls"},
                    "id": "tc1",
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TOOL_START
        assert event.data["tool_name"] == "bash"

    def test_tool_result_event(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "tool_result",
                    "tool_use_id": "tc1",
                    "content": "ok",
                    "is_error": False,
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TOOL_RESULT

    def test_result_event_ignored(self) -> None:
        event = _parse(
            json.dumps({"type": "result", "result": "final answer"}),
            "s1",
        )
        assert event is None

    def test_error_event_dict(self) -> None:
        event = _parse(
            json.dumps({"type": "error", "error": {"message": "rate limited"}}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.ERROR

    def test_error_event_string(self) -> None:
        event = _parse(
            json.dumps({"type": "error", "error": "something broke"}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.ERROR

    def test_invalid_json_yields_text_delta(self) -> None:
        event = _parse("not json at all", "s1")
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert "not json at all" in event.data["content"]

    def test_non_dict_json_yields_text_delta(self) -> None:
        event = _parse(json.dumps([1, 2, 3]), "s1")
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA

    def test_unknown_type_returns_none(self) -> None:
        event = _parse(
            json.dumps({"type": "unknown_event", "data": "x"}),
            "s1",
        )
        assert event is None

    def test_empty_content_string(self) -> None:
        event = _parse(
            json.dumps({"type": "assistant", "content": ""}),
            "s1",
        )
        assert event is None

    def test_codex_agent_message(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "id": "0",
                    "msg": {"type": "agent_message", "message": "hello from codex"},
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert event.data["content"] == "hello from codex"

    def test_codex_task_started_ignored(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "id": "0",
                    "msg": {"type": "task_started", "model_context_window": None},
                }
            ),
            "s1",
        )
        assert event is None

    def test_codex_token_count(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "id": "0",
                    "msg": {"type": "token_count", "info": None, "rate_limits": None},
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.USAGE_UPDATE

    def test_codex_stream_error(self) -> None:
        event = _parse(
            json.dumps({"id": "0", "msg": {"type": "stream_error", "message": "rate limited"}}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.ERROR

    def test_codex_error(self) -> None:
        event = _parse(
            json.dumps({"id": "0", "msg": {"type": "error", "message": "model not supported"}}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.ERROR

    def test_codex_init_line_ignored(self) -> None:
        event = _parse(
            json.dumps({"provider": "aliyun", "model": "MiniMax-M2.5", "sandbox": "read-only"}),
            "s1",
        )
        assert event is None

    def test_codex_prompt_line_ignored(self) -> None:
        event = _parse(
            json.dumps({"prompt": "hello"}),
            "s1",
        )
        assert event is None


class TestCodexItemFormat:
    """Tests for Codex new format (item.* / turn.* events)."""

    def test_item_completed_agent_message(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_3", "type": "agent_message", "text": "Done."},
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert event.data["content"] == "Done."

    def test_item_completed_reasoning(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "reasoning",
                        "text": "Scanning docs...",
                    },
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.REASONING_DELTA
        assert event.data["content"] == "Scanning docs..."

    def test_item_started_command_execution(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.started",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": "bash -lc ls",
                        "aggregated_output": "",
                        "exit_code": None,
                        "status": "in_progress",
                    },
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TOOL_START
        assert event.data["tool_name"] == "command_execution"
        assert event.data["tool_input"]["command"] == "bash -lc ls"
        assert event.data["tool_call_id"] == "item_1"

    def test_item_completed_command_execution_success(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": "bash -lc ls",
                        "aggregated_output": "docs\nsrc\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TOOL_RESULT
        assert event.data["output"] == "docs\nsrc\n"
        assert event.data["is_error"] is False

    def test_item_completed_command_execution_failed(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "command_execution",
                        "command": "bash -lc false",
                        "aggregated_output": "",
                        "exit_code": 1,
                        "status": "failed",
                    },
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TOOL_RESULT
        assert event.data["is_error"] is True

    def test_item_completed_file_change(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_4",
                        "type": "file_change",
                        "changes": [
                            {"path": "docs/new.md", "kind": "add"},
                            {"path": "docs/old.md", "kind": "update"},
                        ],
                        "status": "completed",
                    },
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TOOL_RESULT
        assert "add docs/new.md" in event.data["output"]
        assert "update docs/old.md" in event.data["output"]
        assert event.data["is_error"] is False

    def test_item_completed_error(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_9",
                        "type": "error",
                        "message": "command output truncated",
                    },
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.STATUS_UPDATE
        assert event.data["status"] == "warning"
        assert event.data["message"] == "command output truncated"

    def test_turn_completed_with_usage(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "turn.completed",
                    "usage": {
                        "input_tokens": 24763,
                        "cached_input_tokens": 24448,
                        "output_tokens": 122,
                    },
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.USAGE_UPDATE
        assert event.data["input_tokens"] == 24763
        assert event.data["output_tokens"] == 122
        assert event.data["cache_read"] == 24448

    def test_turn_failed(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "turn.failed",
                    "error": {"message": "model response stream ended unexpectedly"},
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.ERROR

    def test_thread_started_ignored(self) -> None:
        event = _parse(
            json.dumps({"type": "thread.started", "thread_id": "abc-123"}),
            "s1",
        )
        assert event is None

    def test_turn_started_ignored(self) -> None:
        event = _parse(
            json.dumps({"type": "turn.started"}),
            "s1",
        )
        assert event is None

    def test_item_completed_empty_agent_message(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"id": "item_3", "type": "agent_message", "text": ""},
                }
            ),
            "s1",
        )
        assert event is None

    def test_item_no_item_field(self) -> None:
        event = _parse(
            json.dumps({"type": "item.completed"}),
            "s1",
        )
        assert event is None


class TestEdgeCases:
    """Additional NDJSON parsing edge cases."""

    def test_usage_event_with_info_field(self) -> None:
        event = _parse(
            json.dumps({"type": "usage", "info": {"input_tokens": 500, "output_tokens": 200}}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.USAGE_UPDATE
        assert event.data["input_tokens"] == 500

    def test_usage_event_without_info(self) -> None:
        event = _parse(
            json.dumps({"type": "usage", "input_tokens": 100, "output_tokens": 50}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.USAGE_UPDATE

    def test_text_event_type(self) -> None:
        event = _parse(
            json.dumps({"type": "text", "content": "hello"}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA

    def test_result_event_with_usage(self) -> None:
        event = _parse(
            json.dumps(
                {
                    "type": "result",
                    "usage": {"input_tokens": 1000, "output_tokens": 300},
                }
            ),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.USAGE_UPDATE

    def test_turn_completed_without_usage(self) -> None:
        event = _parse(
            json.dumps({"type": "turn.completed"}),
            "s1",
        )
        assert event is None

    def test_turn_failed_no_error_object(self) -> None:
        event = _parse(
            json.dumps({"type": "turn.failed"}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.ERROR

    def test_agent_message_empty(self) -> None:
        event = _parse(
            json.dumps({"type": "agent_message", "message": ""}),
            "s1",
        )
        assert event is None

    def test_thinking_event(self) -> None:
        event = _parse(
            json.dumps({"type": "thinking", "thinking": "hmm let me think"}),
            "s1",
        )
        assert event is not None
        assert event.type == RuntimeEventType.REASONING_DELTA

    def test_ansi_escapes_are_stripped_from_plain_text_lines(self) -> None:
        event = _parse("\x1b[31;1mError:\x1b[0m Connection failed\r\n")
        assert event is not None
        assert event.type == RuntimeEventType.TEXT_DELTA
        assert event.data["content"] == "Error: Connection failed\n"
