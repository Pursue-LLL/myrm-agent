"""The system's note about a settled background task is not something the user did, so no count of the user's
activity includes it.

Read from the real tables: the evolution metrics, the weekly summary, the session message counts and the behavioral
routine measurement all aggregate user rows in SQL, and the memory-extraction retry picks the last turn a person
opened.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from app.api.companion.router import get_evolution_status
from app.api.statistics.growth_dashboard import _fetch_weekly_summary
from app.api.statistics.session_analytics import get_session_analytics
from app.database import connection
from app.database.dto import MessageDTO
from app.database.models.chat import WAKEUP_NOTICE_DEGRADED, WAKEUP_NOTICE_FOLLOWUP, WAKEUP_NOTICE_KEY, WAKEUP_NOTICE_SUPPRESSED
from app.services.chat.chat_service import ChatService
from app.services.memory.behavioral.measurement_service import BehavioralMeasurementService
from app.services.memory.extract_retry.retry_chat_memory_extract import _find_last_turn

pytestmark = pytest.mark.usefixtures("setup_test_database")

_NOTICE_XML = "<system_notification type='adaptive_wakeup_followup'>job done</system_notification>"
_NOTICE_KINDS = (WAKEUP_NOTICE_FOLLOWUP, WAKEUP_NOTICE_DEGRADED, WAKEUP_NOTICE_SUPPRESSED)


async def _append(chat_id: str, message_id: str, content: str, extra_data: dict[str, object] | None = None) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content=content,
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id=message_id,
        extra_data=extra_data,
    )


@pytest.fixture
async def chat_id() -> str:
    """One chat holding a message the person typed and one note of every kind the wake router writes."""
    chat = str(uuid.uuid4())
    await _append(chat, "person-1", "what the person typed")
    for kind in _NOTICE_KINDS:
        await _append(chat, f"notice-{kind}", _NOTICE_XML, {WAKEUP_NOTICE_KEY: kind})
    return chat


async def test_the_evolution_metrics_count_only_what_the_person_typed(chat_id: str) -> None:
    async with connection.get_session() as db:
        status = await get_evolution_status(current_rarity="Common", db=db)

    assert status.metrics.total_messages == 1
    assert status.metrics.active_days == 1


async def test_the_weekly_summary_counts_only_what_the_person_typed(chat_id: str) -> None:
    summary = await _fetch_weekly_summary()

    assert summary.messages_sent == 1


async def test_the_session_message_counts_leave_the_notes_out(chat_id: str) -> None:
    async with connection.get_session() as db:
        response = await get_session_analytics(chat_id, db=db)

    stats = json.loads(bytes(response.body))["data"]
    assert (stats["message_count"], stats["user_messages"]) == (1, 1)


async def test_the_routine_measurement_reads_only_what_the_person_typed(chat_id: str) -> None:
    async with connection.get_session() as db:
        messages = await BehavioralMeasurementService(db, MagicMock()).collect_behavioral_messages(lookback_days=7)

    assert [message.id for message in messages if message.channel == "webui"] == ["chat:person-1"]


def _row(message_id: str, role: str, extra_data: dict[str, object] | None = None) -> MessageDTO:
    return MessageDTO(
        id=message_id,
        chat_id="chat-1",
        role=role,
        content=message_id,
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        created_at=datetime.now(UTC),
        extra_data=extra_data,
    )


def test_the_memory_retry_works_on_the_last_turn_a_person_opened() -> None:
    rows = [
        _row("person-1", "user"),
        _row("answer-1", "assistant"),
        _row("notice-1", "user", {WAKEUP_NOTICE_KEY: WAKEUP_NOTICE_FOLLOWUP}),
        _row("wake-answer", "assistant"),
    ]

    last_user, last_assistant, history = _find_last_turn(rows)

    assert (last_user.id, last_assistant.id, history) == ("person-1", "answer-1", [])
