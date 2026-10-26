"""What ``TurnParser`` knows across the lines of one turn: the announced session, the verdict and streamed text."""

from __future__ import annotations

import json

from myrm_agent_harness.toolkits.acp.runtime.cli.parser import tool_summary
from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import CliResult, TurnParser
from myrm_agent_harness.toolkits.acp.types import RuntimeEvent, RuntimeEventType

_ID = "11111111-2222-3333-4444-555555555555"


def _feed(parser: TurnParser, *lines: dict[str, object] | str) -> list[RuntimeEvent]:
    events: list[RuntimeEvent] = []
    for line in lines:
        events.extend(parser.feed(line if isinstance(line, str) else json.dumps(line)))
    return events


def _texts(events: list[RuntimeEvent]) -> list[str]:
    return [str(event.data["content"]) for event in events if event.type == RuntimeEventType.TEXT_DELTA]


class TestAnnouncedSession:
    def test_claude_announces_its_session_in_the_init_line(self) -> None:
        parser = TurnParser("s1")

        events = _feed(parser, {"type": "system", "subtype": "init", "session_id": _ID})

        assert events == []
        assert parser.take_announced() == _ID

    def test_codex_announces_its_thread_when_it_starts(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "thread.started", "thread_id": _ID})

        assert parser.take_announced() == _ID

    def test_an_announcement_is_taken_once(self) -> None:
        parser = TurnParser("s1")
        _feed(parser, {"type": "system", "subtype": "init", "session_id": _ID})

        assert parser.take_announced() == _ID
        assert parser.take_announced() is None

    def test_the_result_line_never_announces(self) -> None:
        """A failed resume reports the id it was asked for in ``result``; only the init line proves the CLI has it."""
        parser = TurnParser("s1")

        _feed(parser, {"type": "result", "subtype": "error_during_execution", "is_error": True, "session_id": _ID})

        assert parser.take_announced() is None

    def test_other_system_lines_and_missing_ids_announce_nothing(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "system", "subtype": "api_retry", "session_id": _ID})
        _feed(parser, {"type": "system", "subtype": "init"})
        _feed(parser, {"type": "system", "subtype": "init", "session_id": ""})
        _feed(parser, {"type": "thread.started"})

        assert parser.take_announced() is None


class TestClaudeMessages:
    def test_text_and_tool_calls_keep_the_order_of_their_blocks(self) -> None:
        parser = TurnParser("s1")
        message = {
            "id": "msg_1",
            "content": [
                {"type": "text", "text": "Looking. "},
                {"type": "text", "text": "Now."},
                {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "/work/a.py"}},
                {"type": "text", "text": "Done."},
            ],
        }

        events = _feed(parser, {"type": "assistant", "message": message})

        assert [event.type for event in events] == [
            RuntimeEventType.TEXT_DELTA,
            RuntimeEventType.TOOL_START,
            RuntimeEventType.TEXT_DELTA,
        ]
        assert events[0].data["content"] == "Looking. Now."
        assert events[1].data["tool_name"] == "Read"
        assert events[1].data["tool_call_id"] == "toolu_1"
        assert events[1].data["summary"] == "/work/a.py"
        assert events[2].data["content"] == "Done."

    def test_tool_results_come_back_in_user_lines(self) -> None:
        parser = TurnParser("s1")
        content = [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "file body", "is_error": False}]

        events = _feed(parser, {"type": "user", "message": {"content": content}})

        assert [event.type for event in events] == [RuntimeEventType.TOOL_RESULT]
        assert events[0].data["tool_call_id"] == "toolu_1"
        assert events[0].data["output"] == "file body"
        assert events[0].data["is_error"] is False

    def test_a_tool_result_made_of_blocks_is_joined_and_bounded(self) -> None:
        parser = TurnParser("s1")
        blocks = [{"type": "text", "text": "a" * 1500}, {"type": "text", "text": "b" * 1500}]
        content = [{"type": "tool_result", "tool_use_id": "toolu_1", "content": blocks}]

        events = _feed(parser, {"type": "user", "message": {"content": content}})

        output = str(events[0].data["output"])
        assert len(output) == 2000
        assert output.startswith("a") and output.endswith("b")

    def test_user_lines_without_tool_results_carry_nothing(self) -> None:
        parser = TurnParser("s1")

        assert _feed(parser, {"type": "user", "message": {"content": [{"type": "text", "text": "hi"}]}}) == []
        assert _feed(parser, {"type": "user", "message": {"content": "plain"}}) == []

    def test_the_cli_error_notice_is_not_model_text(self) -> None:
        """Claude prints its own API error as a synthetic assistant message; the ``result`` line reports it."""
        parser = TurnParser("s1")
        notice = {"content": [{"type": "text", "text": "API Error: 400 bad"}]}

        events = _feed(parser, {"type": "assistant", "error": "invalid_request", "message": notice})

        assert events == []


class TestPartialMessages:
    @staticmethod
    def _start(message_id: str = "msg_1") -> dict[str, object]:
        return {
            "type": "stream_event",
            "api_message_id": message_id,
            "event": {"type": "message_start", "message": {"id": message_id}},
        }

    @staticmethod
    def _delta(text: str, message_id: str = "msg_1") -> dict[str, object]:
        delta = {"type": "text_delta", "text": text}
        return {
            "type": "stream_event",
            "api_message_id": message_id,
            "event": {"type": "content_block_delta", "delta": delta},
        }

    @staticmethod
    def _full(text: str, message_id: str = "msg_1") -> dict[str, object]:
        return {"type": "assistant", "message": {"id": message_id, "content": [{"type": "text", "text": text}]}}

    def test_a_streamed_message_is_not_repeated_by_its_full_copy(self) -> None:
        parser = TurnParser("s1")

        events = _feed(parser, self._start(), self._delta("Hel"), self._delta("lo"), self._full("Hello"))

        assert _texts(events) == ["Hel", "lo"]

    def test_the_tool_calls_of_a_streamed_message_still_arrive_with_it(self) -> None:
        parser = TurnParser("s1")
        full = {
            "type": "assistant",
            "message": {
                "id": "msg_1",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}},
                ],
            },
        }

        events = _feed(parser, self._start(), self._delta("Hello"), full)

        assert [event.type for event in events] == [RuntimeEventType.TEXT_DELTA, RuntimeEventType.TOOL_START]

    def test_a_message_that_was_not_streamed_is_emitted_in_full(self) -> None:
        parser = TurnParser("s1")

        events = _feed(parser, self._start("msg_1"), self._delta("one", "msg_1"), self._full("one", "msg_1"))
        events += _feed(parser, self._full("two", "msg_2"))

        assert _texts(events) == ["one", "two"]

    def test_a_reused_message_id_is_streamed_again(self) -> None:
        """A proxy that answers every request with the same message id must not mute the second message."""
        parser = TurnParser("s1")

        events = _feed(parser, self._start(), self._delta("first"), self._full("first"))
        events += _feed(parser, self._start(), self._delta("second"), self._full("second"))

        assert _texts(events) == ["first", "second"]

    def test_a_delta_without_any_message_id_is_left_to_the_full_message(self) -> None:
        parser = TurnParser("s1")
        orphan = {
            "type": "stream_event",
            "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "x"}},
        }

        events = _feed(parser, orphan, self._full("x"))

        assert _texts(events) == ["x"]

    def test_deltas_that_are_not_text_are_ignored(self) -> None:
        parser = TurnParser("s1")
        thinking = {"type": "thinking_delta", "thinking": "hmm"}
        tool_json = {"type": "input_json_delta", "partial_json": "{"}

        for delta in (thinking, tool_json):
            event = {"type": "content_block_delta", "delta": delta}
            assert (
                _feed(parser, self._start(), {"type": "stream_event", "api_message_id": "msg_1", "event": event}) == []
            )
        assert _feed(parser, {"type": "stream_event", "event": "malformed"}) == []


class TestVerdict:
    def test_a_successful_result_is_not_an_error(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "result", "subtype": "success", "is_error": False, "result": "all done"})

        assert parser.result == CliResult(
            is_error=False, subtype="success", message="all done", terminal_reason="", api_error_status=None
        )

    def test_an_error_result_reports_its_errors_list(self) -> None:
        parser = TurnParser("s1")

        _feed(
            parser,
            {
                "type": "result",
                "subtype": "error_max_turns",
                "is_error": True,
                "terminal_reason": "max_turns",
                "errors": ["Reached maximum number of turns (3)", "", "second"],
            },
        )

        assert parser.result is not None
        assert parser.result.is_error is True
        assert parser.result.message == "Reached maximum number of turns (3); second"
        assert parser.result.terminal_reason == "max_turns"

    def test_an_api_error_carries_its_http_status(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "result", "is_error": True, "result": "API Error: 429", "api_error_status": 429})

        assert parser.result is not None
        assert parser.result.api_error_status == 429
        assert parser.result.message == "API Error: 429"

    def test_a_flag_that_is_not_true_is_not_an_error(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "result", "is_error": "yes", "api_error_status": True})

        assert parser.result is not None
        assert parser.result.is_error is False
        assert parser.result.api_error_status is None

    def test_no_result_line_means_no_verdict(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "assistant", "content": "hi"})

        assert parser.result is None


class TestToolSummary:
    def test_it_names_the_path_command_or_query_the_call_works_on(self) -> None:
        assert tool_summary({"file_path": "/work/a.py", "limit": 10}) == "/work/a.py"
        assert tool_summary({"command": "npm test"}) == "npm test"
        assert tool_summary({"pattern": "TODO"}) == "TODO"
        assert tool_summary({"query": "weather"}) == "weather"

    def test_it_keeps_one_short_line(self) -> None:
        assert tool_summary({"command": "echo a\necho b"}) == "echo a"
        long = tool_summary({"command": "x" * 200})
        assert len(long) == 80
        assert long.endswith("…")

    def test_it_is_empty_when_nothing_fits(self) -> None:
        assert tool_summary({"limit": 10}) == ""
        assert tool_summary({"command": "   "}) == ""
        assert tool_summary("not a dict") == ""
        assert tool_summary(None) == ""
