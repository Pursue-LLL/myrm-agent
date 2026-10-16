"""Finalize settles the HITL card a resume answered, keeps how it was answered, and never touches the next card.

The chat rows are a stateful in-memory stand-in shared by persistence, lookup and card marking, so the order of
"mark the answered card" and "persist the continuation" decides which stored card each step sees.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.stream_session.stream_finalize import finalize_agent_stream_session
from app.services.agent.stream_session.stream_loop import ApprovalTimeoutHolder, ClarificationTimeoutHolder

CHAT_ID = "chat-hitl-cards"
_FORM: dict[str, object] = {"questions": [{"id": "stack", "prompt": "Which stack?"}]}
_USER_RECORD = {"by": "user"}


def _row(row_id: str, role: str, extra_data: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(id=row_id, role=role, extra_data=extra_data)


class _ChatRows:
    """The persisted rows of one chat, as seen by finalize and by the card-marking helpers."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    async def persist(
        self, _chat_id: str, _content: str, *, extra_data: dict[str, object] | None = None, **_kwargs: object
    ) -> None:
        self.rows.append(_row(f"row-{len(self.rows)}", "assistant", dict(extra_data or {})))

    async def get_all(self, _chat_id: str) -> list[SimpleNamespace]:
        return list(self.rows)

    async def update(self, message_id: str, extra_data: dict[str, object]) -> None:
        next(row for row in self.rows if row.id == message_id).extra_data = extra_data

    def card(self, row_id: str, key: str) -> dict[str, object]:
        card = next(row for row in self.rows if row.id == row_id).extra_data[key]
        assert isinstance(card, dict)
        return card


@pytest.fixture
def chat() -> Iterator[_ChatRows]:
    rows = _ChatRows([_row("user-1", "user", {})])
    with (
        patch("app.services.chat.chat_service.ChatService.persist_assistant_message_safe", new=rows.persist),
        patch("app.services.chat.chat_service.ChatService.get_all_messages", new=rows.get_all),
        patch("app.services.chat.chat_service.ChatService.update_message_extra_data", new=rows.update),
    ):
        yield rows


def _session(resume_value: dict[str, object] | None, new_cards: dict[str, object]) -> MagicMock:
    """A finished resume run whose continuation text carries ``new_cards``."""
    session = MagicMock()
    session.pending_session_draft = None
    session.request.chat_id = CHAT_ID
    session.request.message_id = "user-1"
    session.request.resume_value = resume_value
    session.request.timezone = "UTC"
    session.request.use_workflow = False
    session.request.migration_readiness_anchor = None
    session.cancel_token.is_cancelled = False
    session.params.message_id = "user-1"
    session.params.enable_skill_manage = False
    session.collector.has_persistable_turn = True
    session.collector.has_content = True
    session.collector.content = "continued"
    session.collector.extra_data = dict(new_cards)
    session.collector.sibling_group_id = None
    session.collector.has_pending_hitl_replay = MagicMock(return_value=False)
    session.extra_context = {}
    session.stream_ttft_ms = None
    session.had_fatal_error = False
    return session


async def _finalize(session: MagicMock, clarification: ClarificationTimeoutHolder) -> None:
    with ExitStack() as stack:
        for target in (
            "enqueue_context_compaction_telemetry",
            "clear_context_task_metrics",
            "CancellationRegistry",
            "SteeringRegistry",
            "arm_interrupt_timeout",
        ):
            stack.enter_context(patch(f"app.services.agent.stream_session.stream_finalize.{target}"))
        stack.enter_context(patch("app.services.agent.goals.goal_registry.GoalRegistry"))
        stack.enter_context(patch("app.services.agent.stream_session.stream_finalize.user_credentials_ctx"))
        await finalize_agent_stream_session(session, MagicMock(), ApprovalTimeoutHolder(), clarification)


def _stored(card: dict[str, object]) -> dict[str, object]:
    return {"answered": False, **card}


@pytest.mark.asyncio
async def test_a_resume_records_the_users_clarification_answer(chat: _ChatRows) -> None:
    chat.rows.append(_row("asked", "assistant", {"clarification": _stored({"form": _FORM})}))

    await _finalize(_session({"stack": ["fastapi"]}, {}), ClarificationTimeoutHolder())

    card = chat.card("asked", "clarification")
    assert card["answered"] is True
    assert card["answerRecord"] == {**_USER_RECORD, "value": {"stack": ["fastapi"]}}


@pytest.mark.asyncio
async def test_an_answer_that_leads_to_a_new_clarification_settles_the_old_card_and_keeps_the_new_one_open(
    chat: _ChatRows,
) -> None:
    chat.rows.append(_row("asked", "assistant", {"clarification": _stored({"form": _FORM})}))
    follow_up = _session({"stack": ["fastapi"]}, {"clarification": _stored({"form": _FORM})})

    await _finalize(follow_up, ClarificationTimeoutHolder(pending=True))

    assert chat.card("asked", "clarification")["answered"] is True
    assert chat.card("asked", "clarification")["answerRecord"] == {**_USER_RECORD, "value": {"stack": ["fastapi"]}}
    new_card = chat.card("row-2", "clarification")
    assert new_card["answered"] is False
    assert "answerRecord" not in new_card


@pytest.mark.asyncio
async def test_a_card_that_cannot_be_marked_does_not_lose_the_continuation(chat: _ChatRows) -> None:
    chat.rows.append(_row("asked", "assistant", {"clarification": _stored({"form": _FORM})}))

    async def locked(_chat_id: str) -> list[SimpleNamespace]:
        raise RuntimeError("database is locked")

    with patch("app.services.chat.chat_service.ChatService.get_all_messages", new=locked):
        await _finalize(_session({"stack": ["fastapi"]}, {}), ClarificationTimeoutHolder())

    assert [row.id for row in chat.rows if row.id != "asked" and row.role == "assistant"] == ["row-2"]
    assert chat.card("asked", "clarification")["answered"] is False
