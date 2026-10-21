"""Unit tests: the undo helpers of the rollback E2E.

The user presses the undo hint again when a hot reload folded Task Steps, but only a few times; a failure report
survives a page that cannot be evaluated; the test acts only after the page's request queue drained.
"""

from __future__ import annotations

from typing import cast

import pytest

from tests.e2e.test_skill_manage_undo_hint_chrome_e2e import _CLICK_OPEN_STEPS_JS, _ROLLBACK_VISIBLE_JS
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import (
    _QUIET_API_DEADLINE_SEC,
    _ROLLBACK_DIAGNOSTICS_JS,
    describe_chat_page,
    show_rollback_button,
    wait_until_api_is_quiet,
)
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage
from tests.support.chrome_skill_undo_probes import UNDO_STATE_JS

_MODULE = "tests.e2e.test_skill_manage_undo_rollback_chrome_e2e"
_CHAT_URL = "http://ui.test/chat1"
_PAGE_STATE = "page state: steps folded"


class _Page:
    """A chat page that answers each hint press and each Undo-button wait from a script."""

    def __init__(self, *, presses: list[bool], shown: list[bool]) -> None:
        self._presses = iter(presses)
        self._shown = iter(shown)
        self.pressed = 0

    def evaluate(self, _page: object, js: str, *, timeout_sec: float) -> dict[str, object]:
        assert js == _CLICK_OPEN_STEPS_JS
        self.pressed += 1
        return {"ok": next(self._presses)}

    def wait_for_state(self, _client: object, _page: object, js: str, **_kwargs: object) -> dict[str, object]:
        if js == _ROLLBACK_VISIBLE_JS and not next(self._shown):
            raise AssertionError("Undo button not visible")
        return {"ready": True}


def _describe() -> str:
    return _PAGE_STATE


def _show(monkeypatch: pytest.MonkeyPatch, page: _Page) -> None:
    monkeypatch.setattr(f"{_MODULE}.wait_for_state", page.wait_for_state)
    show_rollback_button(cast(ChromeMcpClient, page), cast(McpPage, object()), _CHAT_URL, describe=_describe)


def test_the_first_press_that_shows_the_undo_button_is_the_only_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _Page(presses=[True], shown=[True])

    _show(monkeypatch, page)

    assert page.pressed == 1
    assert "E2E_UNDO_REOPEN" not in capsys.readouterr().out


def test_task_steps_folded_again_by_a_remount_are_opened_by_another_press(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _Page(presses=[True, True], shown=[False, True])

    _show(monkeypatch, page)

    assert page.pressed == 2
    printed = capsys.readouterr().out
    assert printed.count("E2E_UNDO_REOPEN") == 1
    assert f"attempt=1/3 {_PAGE_STATE}" in printed


def test_a_press_that_found_no_hint_because_the_page_remounted_is_pressed_again(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    page = _Page(presses=[False, True], shown=[True])

    _show(monkeypatch, page)

    assert page.pressed == 2
    assert capsys.readouterr().out.count("E2E_UNDO_REOPEN") == 1


def test_a_button_that_never_shows_fails_after_three_presses_with_the_page_state(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _Page(presses=[True, True, True], shown=[False, False, False])

    with pytest.raises(pytest.fail.Exception, match="rollback button not visible after 3 attempts") as failure:
        _show(monkeypatch, page)

    assert page.pressed == 3
    assert _PAGE_STATE in str(failure.value)


class _Probes:
    """A page that answers the two report probes, or fails one of them."""

    def __init__(self, *, store: dict[str, object] | Exception, controls: dict[str, object]) -> None:
        self._answers: dict[str, dict[str, object] | Exception] = {UNDO_STATE_JS: store, _ROLLBACK_DIAGNOSTICS_JS: controls}

    def evaluate(self, _page: object, js: str, *, timeout_sec: float) -> dict[str, object]:
        answer = self._answers[js]
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_a_failure_report_shows_how_far_the_store_got_loading_the_chat_and_what_the_undo_controls_show() -> None:
    page = _Probes(store={"chatId": "chat1", "isMessagesLoaded": False, "loadError": True}, controls={"hintInDom": False})

    report = describe_chat_page(cast(ChromeMcpClient, page), cast(McpPage, object()))

    assert report == (
        'chat store: {"chatId": "chat1", "isMessagesLoaded": false, "loadError": true}\nundo controls: {"hintInDom": false}'
    )


def test_a_page_that_cannot_be_evaluated_is_reported_without_hiding_the_other_probe() -> None:
    page = _Probes(store=RuntimeError("page closed"), controls={"hintInDom": False})

    report = describe_chat_page(cast(ChromeMcpClient, page), cast(McpPage, object()))

    assert "chat store: unavailable (page closed)" in report
    assert 'undo controls: {"hintInDom": false}' in report


def _gate(monkeypatch: pytest.MonkeyPatch, queue: dict[str, object], asked: list[float]) -> None:
    def drain(_evaluate: object, _api_url: str, *, deadline_sec: float) -> dict[str, object]:
        asked.append(deadline_sec)
        return queue

    monkeypatch.setattr(f"{_MODULE}.wait_for_api_queue_to_drain", drain)
    wait_until_api_is_quiet(cast(ChromeMcpClient, object()), cast(McpPage, object()), "http://api.test", stage="before-undo")


def test_a_drained_queue_lets_the_test_act_and_the_stage_is_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked: list[float] = []

    _gate(monkeypatch, {"outcome": "drained", "probes": 3}, asked)

    assert asked == [_QUIET_API_DEADLINE_SEC]
    assert "E2E_API_QUEUE_GATE: stage=before-undo" in capsys.readouterr().out


def test_a_queue_that_never_drains_stops_the_test_with_what_the_probes_saw(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(AssertionError, match="deadline.*connect timeout"):
        _gate(monkeypatch, {"outcome": "deadline", "probes": 90, "last": {"error": "connect timeout"}}, [])
