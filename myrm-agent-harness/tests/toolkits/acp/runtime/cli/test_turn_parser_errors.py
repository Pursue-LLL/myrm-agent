"""How ``TurnParser`` reads the CLIs' failure reports: ``error`` lines are notices; ``turn.failed`` and ``result`` judge."""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.acp.runtime.cli.parser import error_message
from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import TurnParser
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, RuntimeEventType

# The retry notice codex 0.164 prints for every failed request (ids shortened); the verdict comes later.
_RETRY = (
    "Reconnecting... 2/5 (unexpected status 401 Unauthorized: Unknown error, url: wss://api.openai.com/v1/responses, "
    "request id: req_1, auth error: 401, auth error code: invalid_api_key)"
)
_UNAUTHORIZED = (
    "unexpected status 401 Unauthorized: Missing bearer or basic authentication in header, "
    "url: https://api.openai.com/v1/responses, request id: req_2"
)


def _feed(parser: TurnParser, data: dict[str, object]):
    return parser.feed(json.dumps(data))


class TestErrorMessage:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [
            ({"error": {"message": "rate limited"}}, "rate limited"),
            ({"error": "something broke"}, "something broke"),
            ({"message": "codex puts it at the top"}, "codex puts it at the top"),
            ({"error": "", "message": "fallback"}, "fallback"),
            ({"error": None, "message": "from message"}, "from message"),
            ({"error": {"code": 7}}, "{'code': 7}"),
            ({"error": {}}, "none given"),
            ({}, "none given"),
        ],
    )
    def test_the_text_is_where_the_cli_put_it(self, data: dict[str, object], expected: str) -> None:
        assert error_message(data, "none given") == expected


class TestErrorLinesAreNotices:
    """Codex reports every retry of a request as an ``error`` line, and a turn can recover from them."""

    def test_a_retry_notice_is_remembered_and_is_not_an_event(self) -> None:
        parser = TurnParser("s1")

        assert _feed(parser, {"type": "error", "message": _RETRY}) == []
        assert parser.notice == _RETRY

    @pytest.mark.parametrize(
        "line",
        [
            {"type": "error", "error": {"message": "nested object"}},
            {"type": "error", "error": "nested string"},
            {"id": "0", "msg": {"type": "stream_error", "message": "nested object"}},
            {"id": "0", "msg": {"type": "error", "message": "nested object"}},
        ],
    )
    def test_every_shape_of_an_error_line_is_a_notice(self, line: dict[str, object]) -> None:
        parser = TurnParser("s1")

        assert _feed(parser, line) == []
        assert parser.notice.startswith("nested ")

    def test_the_last_notice_is_the_one_kept(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "error", "message": "first"})
        _feed(parser, {"type": "error", "message": "second"})

        assert parser.notice == "second"

    def test_a_turn_without_error_lines_has_no_notice(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}})

        assert parser.notice == ""


class TestTurnFailed:
    def test_a_rejected_login_is_an_auth_failure_with_the_cli_own_text(self) -> None:
        events = _feed(TurnParser("s1"), {"type": "turn.failed", "error": {"message": _UNAUTHORIZED}})

        assert [event.type for event in events] == [RuntimeEventType.ERROR]
        error = events[0].data["error"]
        assert error.code is AcpErrorCode.AUTH_FAILED
        assert error.message == _UNAUTHORIZED
        assert error.retryable is False

    @pytest.mark.parametrize(
        "message",
        [
            # 403 is also a blocked region or an organization policy, so it is not taken for a login problem.
            "unexpected status 403 Forbidden: Country, region, or territory not supported",
            "unexpected status 4010 Unknown",
            "Quota exceeded. Check your plan and billing details.",
            "model response stream ended unexpectedly",
        ],
    )
    def test_any_other_failure_is_unknown_and_keeps_its_text(self, message: str) -> None:
        events = _feed(TurnParser("s1"), {"type": "turn.failed", "error": {"message": message}})

        error = events[0].data["error"]
        assert error.code is AcpErrorCode.UNKNOWN
        assert error.message == message

    def test_a_failure_without_text_still_says_something(self) -> None:
        events = _feed(TurnParser("s1"), {"type": "turn.failed"})

        assert events[0].data["error"].message == "Turn failed"


class TestClaudeErrorCategory:
    """Claude names what went wrong on the synthetic message it prints before its ``result`` line."""

    @staticmethod
    def _error_message(category: str, text: str) -> dict[str, object]:
        message = {"model": "<synthetic>", "content": [{"type": "text", "text": text}]}
        return {"type": "assistant", "error": category, "message": message}

    def test_the_category_reaches_the_verdict_when_there_is_no_api_status(self) -> None:
        parser = TurnParser("s1")

        assert _feed(parser, self._error_message("authentication_failed", "Not logged in · Please run /login")) == []
        _feed(
            parser,
            {
                "type": "result",
                "subtype": "success",
                "is_error": True,
                "api_error_status": None,
                "result": "Not logged in · Please run /login",
            },
        )

        assert parser.result is not None
        assert parser.result.assistant_error == "authentication_failed"
        assert parser.result.api_error_status is None
        assert parser.result.message == "Not logged in · Please run /login"

    def test_the_last_category_wins(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, self._error_message("rate_limit", "slow down"))
        _feed(parser, self._error_message("invalid_request", "bad"))
        _feed(parser, {"type": "result", "subtype": "success", "is_error": True, "result": "bad"})

        assert parser.result is not None
        assert parser.result.assistant_error == "invalid_request"

    def test_a_verdict_without_an_error_message_has_no_category(self) -> None:
        parser = TurnParser("s1")

        _feed(parser, {"type": "result", "subtype": "success", "is_error": False, "result": "done"})

        assert parser.result is not None
        assert parser.result.assistant_error == ""
