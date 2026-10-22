"""Unit tests: the live undo test tolerates a missed hint only when the page proves its chat store was swapped."""

from __future__ import annotations

from typing import cast

import pytest

from tests.e2e.test_skill_manage_live_agent_chrome_e2e import _LiveTurn, _wait_for_undo_hint
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage

_MODULE = "tests.e2e.test_skill_manage_live_agent_chrome_e2e"
_TURN = _LiveTurn(chat_id="chat1", chat_url="http://ui.test/chat1", api_url="http://api.test", started_at=1.0)
_PERSISTED = [{"progressSteps": [{"tool_name": "skill_manage_tool", "skill_mutation_batch_id": "batch-7"}]}]


class _Client:
    """A page whose store state is fixed; records what the test evaluated in it."""

    def __init__(self, state: object) -> None:
        self.state = state
        self.evaluated: list[str] = []

    def evaluate(self, page: object, js: str, *, timeout_sec: float) -> object:
        self.evaluated.append(js)
        return self.state


class _Calls:
    """What the test did to the page besides evaluating scripts."""

    def __init__(self) -> None:
        self.reloads: list[str | None] = []
        self.ui_waits: list[str] = []


def _wait(monkeypatch: pytest.MonkeyPatch, client: _Client, calls: _Calls, *, hint_shows_first: bool) -> None:
    misses = iter([] if hint_shows_first else ["hint never ready"])

    def wait_for_state(*_args: object, **_kwargs: object) -> dict[str, object]:
        for missed in misses:
            raise AssertionError(missed)
        return {"ready": True}

    monkeypatch.setattr(f"{_MODULE}.wait_for_state", wait_for_state)
    monkeypatch.setattr(f"{_MODULE}.stored_messages", lambda *_args: _PERSISTED)
    monkeypatch.setattr(f"{_MODULE}.recently_edited_frontend_files", lambda _since: ["store/chat/clarificationState.ts"])
    monkeypatch.setattr(f"{_MODULE}.reload_mcp_page", lambda _client, _page, *, target_url=None: calls.reloads.append(target_url))
    monkeypatch.setattr(f"{_MODULE}._wait_for_ui", lambda *_args, **kwargs: calls.ui_waits.append(str(kwargs["what"])))
    _wait_for_undo_hint(cast(ChromeMcpClient, client), cast(McpPage, object()), _TURN)


def test_a_hint_that_shows_up_needs_no_diagnosis_and_no_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    client, calls = _Client({"storeReplaced": True}), _Calls()

    _wait(monkeypatch, client, calls, hint_shows_first=True)

    assert client.evaluated == []
    assert calls.reloads == []
    assert calls.ui_waits == []


def test_a_swapped_store_makes_the_user_reload_the_chat_once_and_wait_for_the_hint_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client, calls = _Client({"storeReplaced": True}), _Calls()

    _wait(monkeypatch, client, calls, hint_shows_first=False)

    assert len(client.evaluated) == 1
    assert calls.reloads == [_TURN.chat_url]
    assert len(calls.ui_waits) == 1
    assert "after reloading the chat" in calls.ui_waits[0]
    printed = capsys.readouterr().out
    assert "E2E_UNDO_RELOAD" in printed
    assert "clarificationState.ts" in printed


@pytest.mark.parametrize("state", [{"storeReplaced": False}, {"storeReplaced": None}, "not a state"])
def test_a_miss_without_proof_of_a_swapped_store_fails_with_what_the_page_and_server_held(
    monkeypatch: pytest.MonkeyPatch, state: object
) -> None:
    client, calls = _Client(state), _Calls()

    with pytest.raises(pytest.fail.Exception) as failure:
        _wait(monkeypatch, client, calls, hint_shows_first=False)

    message = str(failure.value)
    assert "undo hint did not appear: hint never ready" in message
    assert "skill_manage_tool" in message
    assert "batch-7" in message
    assert "clarificationState.ts" in message
    assert calls.reloads == []
    assert calls.ui_waits == []
