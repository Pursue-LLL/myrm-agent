"""How a real-model test turn gets past the approvals a model asks for: each one is answered once, and only the approvals still pending are answered."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from fastapi.testclient import TestClient

from tests.support import real_model_workspace_turns as turns
from tests.support.real_model_workspace_turns import perform_agent_stream

Events = list[dict[str, object]]

_APPROVAL: Events = [{"type": "tool_approval_request"}, {"type": "message_end"}]


def _said(text: str) -> Events:
    return [{"type": "message", "data": text}, {"type": "message_end"}]


class _Server:
    """Answers each request of a turn with the next scripted stream, and keeps the requests the test client sent."""

    def __init__(self, streams: list[Events]) -> None:
        self._streams = iter(streams)
        self.requests: list[dict[str, object]] = []

    def stream(self, client: TestClient, request_data: dict[str, object]) -> Events:
        self.requests.append(request_data)
        return next(self._streams)


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[Events]], _Server]:
    def install(streams: list[Events]) -> _Server:
        server = _Server(streams)
        monkeypatch.setattr(turns, "stream_turn", server.stream)
        return server

    return install


def _run(model_selection: dict[str, object] | None = None) -> tuple[str, Events, int]:
    return perform_agent_stream(cast(TestClient, None), "question", "chat-1", model_selection=model_selection or {"model": "m"})


class TestATurnWithoutApprovals:
    def test_is_one_request_and_its_answer(self, serve: Callable[[list[Events]], _Server]) -> None:
        server = serve([_said("hello")])

        answer, collected, tool_calls = _run()

        assert len(server.requests) == 1
        assert "resumeValue" not in server.requests[0]
        assert answer == "hello"
        assert collected == _said("hello")
        assert tool_calls == 0

    def test_counts_the_tool_calls_of_the_stream(self, serve: Callable[[list[Events]], _Server]) -> None:
        serve([[{"type": "tasks_steps", "tool_name": "bash"}, {"type": "tasks_steps"}, *_said("done")]])

        _, _, tool_calls = _run()

        assert tool_calls == 1


class TestAnApprovalTheModelAsksFor:
    def test_is_answered_by_one_resume_and_the_answer_is_what_follows_it(self, serve: Callable[[list[Events]], _Server]) -> None:
        """The stopped turn's approval event stays in everything collected; it must not make the turn look stopped again after it was answered."""
        server = serve([_APPROVAL, _said("after the approval")])

        answer, collected, _ = _run()

        assert len(server.requests) == 2
        assert answer == "after the approval"
        assert collected == [*_APPROVAL, *_said("after the approval")]

    def test_resume_is_what_the_ui_sends_under_an_id_of_its_own(self, serve: Callable[[list[Events]], _Server]) -> None:
        """Under the stopped turn's id the server answers with that turn's buffered events and never with what follows, so the pending approval would look unanswered."""
        server = serve([_APPROVAL, _said("ok")])

        _run({"model": "m"})

        first, resume = server.requests
        assert resume["messageId"] != first["messageId"]
        assert resume["query"] == ""
        assert resume["resumeValue"] == {"decisions": [{"type": "approve", "extensions": {"allowAlways": True}}]}
        for key in ("chatId", "modelSelection", "actionMode"):
            assert resume[key] == first[key]

    def test_a_second_approval_after_the_first_is_answered_too(self, serve: Callable[[list[Events]], _Server]) -> None:
        server = serve([_APPROVAL, _APPROVAL, _said("finally")])

        answer, _, _ = _run()

        assert len(server.requests) == 3
        assert answer == "finally"
        assert len({request["messageId"] for request in server.requests}) == 3

    def test_that_never_stops_asking_fails_instead_of_passing_unanswered(self, serve: Callable[[list[Events]], _Server]) -> None:
        server = serve([_APPROVAL] * (turns._MAX_APPROVAL_ROUNDS + 1))

        with pytest.raises(AssertionError, match="still waiting for an approval"):
            _run()

        assert len(server.requests) == turns._MAX_APPROVAL_ROUNDS + 1
