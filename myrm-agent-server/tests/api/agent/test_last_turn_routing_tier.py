"""What a retry replaces, read from the real message table: the answers of the latest user turn.

A turn can end with rows the system appended on its own. Background-job and voice-task notices are not answers: they
carry no `routingTier`, a retry must leave them active and out of the version group, and the version count must not
include them. The retried answer's tier must still be found, an older turn's tier must never stand in for it, and the
rows read must be exactly the rows a retry deactivates.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from myrm_agent_harness.toolkits.llms.routing.complexity_router import RoutingTier
from sqlalchemy import select

from app.core.types import ModelConfig
from app.database import connection
from app.database.models import Chat, Message
from app.database.models.chat import BACKGROUND_JOB_NOTICE_KEY, VOICE_BACKGROUND_TASK_NOTICE_KEY
from app.database.repositories.chat_repo import ChatRepository
from app.services.agent.params.routing_memory import complaint_floor, load_retry_baseline

pytestmark = pytest.mark.usefixtures("setup_test_database")

_BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class _Row:
    role: str
    extra_data: dict[str, object] | None = None
    is_active: bool = True


def _user() -> _Row:
    return _Row("user")


def _answer(tier: str | None = None, *, is_active: bool = True) -> _Row:
    return _Row("assistant", {"routingTier": tier} if tier else {"modelName": "m"}, is_active)


_BACKGROUND_NOTICE = _Row("assistant", {BACKGROUND_JOB_NOTICE_KEY: True})
_VOICE_NOTICE = _Row("assistant", {VOICE_BACKGROUND_TASK_NOTICE_KEY: True})
_NO_EXTRA_DATA = _Row("assistant", None)


async def _seed_chat(rows: list[_Row], *, same_timestamp: bool = False) -> str:
    """Insert *rows* in order; ids ascend, so with one shared timestamp the id alone orders them."""
    chat_id = str(uuid.uuid4())
    async with connection.get_session() as db:
        db.add(Chat(id=chat_id, title="Test", created_at=_BASE_TIME))
        for index, row in enumerate(rows):
            created_at = _BASE_TIME if same_timestamp else _BASE_TIME + timedelta(seconds=index)
            db.add(
                Message(
                    id=f"{chat_id}-m{index:03d}",
                    chat_id=chat_id,
                    role=row.role,
                    content=f"{row.role} {index}",
                    sent_at=created_at,
                    sent_timezone="UTC",
                    created_at=created_at,
                    extra_data=row.extra_data,
                    is_active=row.is_active,
                )
            )
        await db.commit()
    return chat_id


async def _last_turn_tier(chat_id: str) -> str | None:
    async with connection.get_session() as db:
        return await ChatRepository.get_last_turn_routing_tier(db, chat_id)


class TestLastTurnRoutingTier:
    async def test_is_the_tier_recorded_by_the_answer_of_the_latest_turn(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("standard")])

        assert await _last_turn_tier(chat_id) == "standard"

    @pytest.mark.parametrize(
        "trailing",
        [_BACKGROUND_NOTICE, _VOICE_NOTICE, _NO_EXTRA_DATA],
        ids=["background-notice", "voice-notice", "no-extra-data"],
    )
    async def test_rows_the_system_appended_after_the_answer_do_not_hide_its_tier(self, trailing: _Row) -> None:
        chat_id = await _seed_chat([_user(), _answer("reasoning"), trailing])

        assert await _last_turn_tier(chat_id) == "reasoning"

    async def test_the_newest_recorded_answer_of_the_turn_wins(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("simple"), _answer("reasoning"), _BACKGROUND_NOTICE])

        assert await _last_turn_tier(chat_id) == "reasoning"

    async def test_an_earlier_turn_never_stands_in_for_an_answer_that_recorded_no_tier(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("reasoning"), _user(), _answer()])

        assert await _last_turn_tier(chat_id) is None

    async def test_answers_already_deactivated_by_the_retry_are_still_read(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("simple", is_active=False)])

        assert await _last_turn_tier(chat_id) == "simple"

    async def test_values_that_are_not_strings_are_ignored(self) -> None:
        chat_id = await _seed_chat([_user(), _Row("assistant", {"routingTier": 3})])

        assert await _last_turn_tier(chat_id) is None

    async def test_the_raw_value_is_returned_for_the_caller_to_classify(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("code")])

        assert await _last_turn_tier(chat_id) == "code"

    async def test_chat_without_a_user_message_or_without_messages_has_no_tier(self) -> None:
        only_assistant = await _seed_chat([_answer("standard")])
        empty = await _seed_chat([])

        assert await _last_turn_tier(only_assistant) is None
        assert await _last_turn_tier(empty) is None
        assert await _last_turn_tier("nonexistent-chat-id") is None


async def _retry(chat_id: str) -> str:
    """Deactivate the latest turn's answers exactly as a regenerate does; returns the version group id."""
    async with connection.get_session() as db:
        last_user = await ChatRepository.get_last_user_message(db, chat_id)
        assert last_user is not None
        _, group_id = await ChatRepository.deactivate_last_assistant_siblings(db, chat_id, last_user)
        await db.commit()
    return group_id


async def _row_states(chat_id: str) -> dict[str, tuple[bool, str | None]]:
    """message id -> (is_active, sibling_group_id)."""
    async with connection.get_session() as db:
        rows = (
            await db.execute(select(Message.id, Message.is_active, Message.sibling_group_id).where(Message.chat_id == chat_id))
        ).all()
    return {row.id: (row.is_active, row.sibling_group_id) for row in rows}


class TestSameRowsAsTheRetry:
    async def test_reads_exactly_the_rows_a_retry_deactivates_when_timestamps_tie(self) -> None:
        """Order within one timestamp is by id: the first answer belongs to the previous turn, the rest to the latest."""
        chat_id = await _seed_chat(
            [_answer("reasoning"), _user(), _answer("simple"), _BACKGROUND_NOTICE],
            same_timestamp=True,
        )

        await _retry(chat_id)

        states = await _row_states(chat_id)
        assert {row_id for row_id, (is_active, _) in states.items() if not is_active} == {f"{chat_id}-m002"}
        assert await _last_turn_tier(chat_id) == "simple"


class TestRetryLeavesSystemNoticesAlone:
    @pytest.mark.parametrize("notice", [_BACKGROUND_NOTICE, _VOICE_NOTICE], ids=["background-notice", "voice-notice"])
    async def test_a_notice_stays_active_and_outside_the_version_group(self, notice: _Row) -> None:
        chat_id = await _seed_chat([_user(), _answer("simple"), notice])

        group_id = await _retry(chat_id)

        states = await _row_states(chat_id)
        assert states[f"{chat_id}-m001"] == (False, group_id)
        assert states[f"{chat_id}-m002"] == (True, None)

    async def test_the_version_count_covers_answers_only(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("simple"), _BACKGROUND_NOTICE])
        group_id = await _retry(chat_id)

        async with connection.get_session() as db:
            db.add(
                Message(
                    id=f"{chat_id}-m003",
                    chat_id=chat_id,
                    role="assistant",
                    content="regenerated",
                    sent_at=_BASE_TIME + timedelta(seconds=3),
                    sent_timezone="UTC",
                    created_at=_BASE_TIME + timedelta(seconds=3),
                    extra_data={"routingTier": "reasoning"},
                    sibling_group_id=group_id,
                )
            )
            await db.commit()
            history = await ChatRepository.get_recent_messages(db, chat_id)
            versions = await ChatRepository.get_sibling_info(db, group_id)

        regenerated = history[-1]
        assert regenerated.id == f"{chat_id}-m003"
        assert (regenerated.sibling_count, regenerated.sibling_index) == (2, 2)
        assert [version["id"] for version in versions] == [f"{chat_id}-m001", f"{chat_id}-m003"]

    async def test_the_history_handed_to_the_agent_keeps_the_notice_after_the_user_turn(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("simple"), _BACKGROUND_NOTICE])
        await _retry(chat_id)

        async with connection.get_session() as db:
            history = await ChatRepository.get_recent_messages(db, chat_id)

        assert [message.id for message in history] == [f"{chat_id}-m000", f"{chat_id}-m002"]

    async def test_a_turn_holding_only_a_notice_has_nothing_to_deactivate(self) -> None:
        chat_id = await _seed_chat([_user(), _VOICE_NOTICE])

        group_id = await _retry(chat_id)

        assert group_id
        assert (await _row_states(chat_id))[f"{chat_id}-m001"] == (True, None)

    async def test_only_a_true_marker_exempts_a_row(self) -> None:
        chat_id = await _seed_chat([_user(), _Row("assistant", {BACKGROUND_JOB_NOTICE_KEY: False})])

        group_id = await _retry(chat_id)

        assert (await _row_states(chat_id))[f"{chat_id}-m001"] == (False, group_id)


class TestRetryBaseline:
    async def test_survives_a_background_notice_after_the_answer(self) -> None:
        """The answer ran the reasoning model; a notice written after it must not reset the baseline to standard."""
        chat_id = await _seed_chat([_user(), _answer("reasoning"), _BACKGROUND_NOTICE])

        assert await load_retry_baseline(chat_id) is RoutingTier.REASONING

    async def test_is_none_for_a_turn_that_ran_the_main_model(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("simple"), _user(), _answer()])

        assert await load_retry_baseline(chat_id) is None

    async def test_a_specialty_hit_has_no_complexity_baseline(self) -> None:
        chat_id = await _seed_chat([_user(), _answer("code")])

        assert await load_retry_baseline(chat_id) is None

    async def test_feeds_the_climb_from_the_real_tier_of_the_retried_answer(self) -> None:
        main = ModelConfig(model="gpt-4o", api_key="sk-main")
        light = ModelConfig(model="gpt-4o-mini", api_key="sk-light")
        reasoning = ModelConfig(model="deepseek-reasoner", api_key="sk-reasoning")
        chat_id = await _seed_chat([_user(), _answer("simple"), _BACKGROUND_NOTICE])

        floor = complaint_floor(await load_retry_baseline(chat_id), standard=main, light=light, reasoning=reasoning)

        assert floor == (RoutingTier.STANDARD, True)

    async def test_without_a_chat_id_there_is_nothing_to_read(self) -> None:
        assert await load_retry_baseline(None) is None
