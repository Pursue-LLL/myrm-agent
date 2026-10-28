"""Which user row retry, regenerate and undo act on when background settlements landed after the last real turn.

Read from the real message table. A settlement the wake router degraded or suppressed starts no turn, so its notice row
is not a turn to redo; a followup notice does open one (the wake turn answers it), so it stays what the last turn is.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupEvent, WakeupSourceType
from sqlalchemy import select

from app.database import connection
from app.database.models import Chat, Message
from app.database.models.chat import (
    WAKEUP_NOTICE_DEGRADED,
    WAKEUP_NOTICE_FOLLOWUP,
    WAKEUP_NOTICE_KEY,
    WAKEUP_NOTICE_SUPPRESSED,
)
from app.database.repositories.chat_repo import ChatRepository
from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.agent.adaptive_wakeup import service as service_module

pytestmark = pytest.mark.usefixtures("setup_test_database")

_BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Row:
    role: str
    content: str
    extra_data: dict[str, object] | None = None


def _typed(text: str) -> _Row:
    return _Row("user", text)


def _answer(text: str) -> _Row:
    return _Row("assistant", text)


def _notice(kind: str) -> _Row:
    return _Row("user", f"notice {kind}", {WAKEUP_NOTICE_KEY: kind})


async def _last_user_content(rows: list[_Row]) -> str | None:
    chat_id = str(uuid.uuid4())
    async with connection.get_session() as db:
        db.add(Chat(id=chat_id, title="Test", created_at=_BASE_TIME))
        for index, row in enumerate(rows):
            created_at = _BASE_TIME + timedelta(seconds=index)
            db.add(
                Message(
                    id=f"{chat_id}-m{index:03d}",
                    chat_id=chat_id,
                    role=row.role,
                    content=row.content,
                    sent_at=created_at,
                    sent_timezone="UTC",
                    created_at=created_at,
                    extra_data=row.extra_data,
                )
            )
        await db.commit()
    async with connection.get_session() as db:
        last_user = await ChatRepository.get_last_user_message(db, chat_id)
    return last_user.content if last_user else None


@pytest.mark.parametrize("kind", [WAKEUP_NOTICE_DEGRADED, WAKEUP_NOTICE_SUPPRESSED])
async def test_a_settlement_that_started_no_turn_is_not_the_turn_to_redo(kind: str) -> None:
    assert await _last_user_content([_typed("write the report"), _answer("done"), _notice(kind)]) == "write the report"


async def test_several_such_settlements_in_a_row_are_all_passed_over() -> None:
    rows = [_typed("write the report"), _answer("done"), _notice(WAKEUP_NOTICE_DEGRADED), _notice(WAKEUP_NOTICE_SUPPRESSED)]

    assert await _last_user_content(rows) == "write the report"


async def test_a_followup_notice_opens_the_wake_turn_and_stays_the_last_turn() -> None:
    rows = [_typed("write the report"), _answer("started"), _notice(WAKEUP_NOTICE_FOLLOWUP), _answer("finished")]

    assert await _last_user_content(rows) == f"notice {WAKEUP_NOTICE_FOLLOWUP}"


async def test_a_message_the_user_typed_after_the_settlement_is_the_last_turn() -> None:
    rows = [_typed("first"), _notice(WAKEUP_NOTICE_SUPPRESSED), _typed("second")]

    assert await _last_user_content(rows) == "second"


async def test_rows_without_extra_data_or_with_other_markers_count_as_typed() -> None:
    rows = [_typed("first"), _Row("user", "with other extra", {"something": "else"})]

    assert await _last_user_content(rows) == "with other extra"


async def test_a_chat_with_only_inert_notices_has_no_turn_to_redo() -> None:
    assert await _last_user_content([_notice(WAKEUP_NOTICE_DEGRADED)]) is None


async def test_the_notice_row_the_service_writes_for_a_degraded_settlement_leaves_the_turn_to_redo_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service_module, "get_event_bus", lambda: MagicMock())
    chat_id = str(uuid.uuid4())
    async with connection.get_session() as db:
        db.add(Chat(id=chat_id, title="Test", created_at=_BASE_TIME))
        db.add(
            Message(
                id=f"{chat_id}-m0",
                chat_id=chat_id,
                role="user",
                content="write the report",
                sent_at=_BASE_TIME,
                sent_timezone="UTC",
                created_at=_BASE_TIME,
            )
        )
        await db.commit()
    service = get_adaptive_wakeup_service()
    while service.router.claim_wake_turn(chat_id):
        pass
    try:
        decision = await service.handle_settlement(
            WakeupEvent(
                source_type=WakeupSourceType.SUBAGENT, source_id="task-1", session_id=chat_id, success=True, summary="done"
            )
        )
    finally:
        service.forget_chat(chat_id)

    assert decision is not None
    async with connection.get_session() as db:
        rows = (await db.execute(select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at))).scalars().all()
        last_user = await ChatRepository.get_last_user_message(db, chat_id)
    assert [row.extra_data for row in rows][1:] == [{WAKEUP_NOTICE_KEY: WAKEUP_NOTICE_DEGRADED}]
    assert last_user is not None
    assert last_user.content == "write the report"
