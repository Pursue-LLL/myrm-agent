"""Stream-layer policy of the history rule: which mode a turn declares and when its completion is recorded."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.stream_session import turn_history_sync
from app.services.agent.stream_session.turn_history_sync import commit_turn_history_sync, resolve_turn_history_mode


def _request(**overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "chat_id": "chat-1",
        "message_id": "req-1",
        "resume_value": None,
        "sibling_group_id": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.fixture
def decide(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value="continue")
    monkeypatch.setattr(turn_history_sync, "decide_history_mode", mock)
    return mock


@pytest.fixture
def commit(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(return_value=True)
    monkeypatch.setattr(turn_history_sync, "commit_history_sync", mock)
    return mock


class TestResolveTurnHistoryMode:
    @pytest.mark.asyncio
    async def test_a_new_message_takes_the_stored_comparison(self, decide: AsyncMock) -> None:
        decide.return_value = "replace"

        mode = await resolve_turn_history_mode(_request(), exclude_message_id="user-1")

        assert mode == "replace"
        decide.assert_awaited_once_with("chat-1", exclude_message_id="user-1")

    @pytest.mark.asyncio
    async def test_a_resume_declares_nothing_because_it_continues_the_thread_it_paused_on(self, decide: AsyncMock) -> None:
        assert await resolve_turn_history_mode(_request(resume_value={"approved": True}), exclude_message_id=None) is None
        decide.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_turn_without_a_chat_declares_nothing(self, decide: AsyncMock) -> None:
        assert await resolve_turn_history_mode(_request(chat_id=None), exclude_message_id=None) is None
        decide.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_regenerate_always_rebuilds_because_the_thread_still_holds_the_replaced_answer(
        self, decide: AsyncMock
    ) -> None:
        assert await resolve_turn_history_mode(_request(sibling_group_id="group-1"), exclude_message_id=None) == "replace"
        decide.assert_not_awaited()


def _session(
    *,
    history_mode: object = "continue",
    chat_id: str | None = "chat-1",
    message_id: str | None = "req-1",
    cancelled: bool = False,
    fatal: bool = False,
    with_economics: bool = True,
) -> SimpleNamespace:
    economics: dict[str, object] = {"turn_context": {"history_mode": history_mode}} if with_economics else {}
    return SimpleNamespace(
        request=_request(chat_id=chat_id, message_id=message_id),
        cancel_token=SimpleNamespace(is_cancelled=cancelled),
        had_fatal_error=fatal,
        collector=SimpleNamespace(extra_data={"tokenEconomics": economics} if with_economics else None),
    )


class TestCommitTurnHistorySync:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["continue", "replace", "resume"])
    async def test_a_turn_that_completed_on_the_thread_is_recorded(self, commit: AsyncMock, mode: str) -> None:
        await commit_turn_history_sync(_session(history_mode=mode), pending_hitl=False)

        commit.assert_awaited_once_with("chat-1", "req-1")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("session", "pending"),
        [
            pytest.param(_session(), True, id="waiting-on-the-user"),
            pytest.param(_session(fatal=True), False, id="failed"),
            pytest.param(_session(cancelled=True), False, id="cancelled"),
            pytest.param(_session(chat_id=None), False, id="no-chat"),
            pytest.param(_session(message_id=None), False, id="no-request-id"),
            pytest.param(_session(history_mode="append"), False, id="thread-not-owned-by-this-server"),
            pytest.param(_session(history_mode=None), False, id="mode-not-reported"),
            pytest.param(_session(with_economics=False), False, id="served-by-another-lane"),
        ],
    )
    async def test_every_other_outcome_records_nothing(
        self,
        commit: AsyncMock,
        session: SimpleNamespace,
        pending: bool,
    ) -> None:
        await commit_turn_history_sync(session, pending_hitl=pending)

        commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_report_of_another_shape_is_not_a_report(self, commit: AsyncMock) -> None:
        session = _session()
        session.collector.extra_data = {"tokenEconomics": {"turn_context": "continue"}}

        await commit_turn_history_sync(session, pending_hitl=False)

        commit.assert_not_awaited()
