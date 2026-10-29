"""Tests for how the shared conversation page treats a long conversation and the times it prints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.security.share.share_locale import ShareLang
from app.database.dto import MessageDTO
from app.database.models.chat import WAKEUP_NOTICE_KEY
from tests.services.chat.share_support import agentless_db, make_chat, make_message, render_page

_CAP = 200
_NOTICE = 'role="note"'


@pytest.fixture
def mock_db() -> MagicMock:
    return agentless_db()


def _turns(count: int) -> list[MessageDTO]:
    """*count* readable messages alternating user / assistant; each content is ``turn-NNN``."""
    return [make_message(f"m{n}", "user" if n % 2 == 0 else "assistant", f"turn-{n:03d}") for n in range(count)]


def _message_blocks(html: str) -> int:
    return html.count('<div class="msg ')


@pytest.mark.parametrize(
    ("lang", "notice", "footer"),
    [
        ("en", "Showing the latest 200 of 350 messages", '<span class="stat">350 messages</span>'),
        ("zh", "仅显示最近 200 条，共 350 条消息", '<span class="stat">350 条消息</span>'),
    ],
    ids=["en", "zh"],
)
async def test_a_long_conversation_shows_its_latest_messages_and_says_how_many_there_are(
    mock_db: MagicMock, lang: ShareLang, notice: str, footer: str
) -> None:
    html = await render_page(mock_db, lang, messages=_turns(350))

    assert _message_blocks(html) == _CAP
    assert "turn-349" in html
    assert "turn-150" in html
    assert "turn-149" not in html
    assert notice in html
    assert footer in html


@pytest.mark.parametrize(
    ("lang", "footer"),
    [("en", '<span class="stat">0 messages</span>'), ("zh", '<span class="stat">0 条消息</span>')],
    ids=["en", "zh"],
)
async def test_an_empty_conversation_says_there_are_no_messages_and_has_no_notice(
    mock_db: MagicMock, lang: ShareLang, footer: str
) -> None:
    html = await render_page(mock_db, lang, messages=[])

    assert _message_blocks(html) == 0
    assert _NOTICE not in html
    assert footer in html


async def test_a_conversation_that_fits_is_shown_whole_without_a_notice(mock_db: MagicMock) -> None:
    html = await render_page(mock_db, "en", messages=_turns(_CAP))

    assert _message_blocks(html) == _CAP
    assert "turn-000" in html
    assert _NOTICE not in html
    assert '<span class="stat">200 messages</span>' in html


async def test_the_notice_comes_before_the_conversation(mock_db: MagicMock) -> None:
    html = await render_page(mock_db, "en", messages=_turns(_CAP + 1))

    assert html.index(_NOTICE) < html.index('<div class="msg ')


async def test_rows_nobody_reads_do_not_use_up_the_window(mock_db: MagicMock) -> None:
    system_rows = [make_message(f"s{n}", "system", f"prompt-{n}") for n in range(120)]
    notices = [
        make_message(
            f"w{n}", "user", f"<system_notification>done-{n}</system_notification>", extra_data={WAKEUP_NOTICE_KEY: "followup"}
        )
        for n in range(120)
    ]

    html = await render_page(mock_db, "en", messages=[*_turns(150), *system_rows, *notices])

    assert _message_blocks(html) == 150
    assert "turn-000" in html
    assert "turn-149" in html
    assert _NOTICE not in html
    assert '<span class="stat">150 messages</span>' in html


async def test_the_total_counts_only_what_a_visitor_can_read(mock_db: MagicMock) -> None:
    system_rows = [make_message(f"s{n}", "system", f"prompt-{n}") for n in range(40)]
    readable = _turns(210)

    html = await render_page(mock_db, "en", messages=[*readable[:100], *system_rows, *readable[100:]])

    assert "Showing the latest 200 of 210 messages" in html
    assert '<span class="stat">210 messages</span>' in html
    assert "turn-010" in html
    assert "turn-009" not in html


@pytest.mark.parametrize(
    "moment",
    [
        datetime(2026, 10, 28, 7, 57),
        datetime(2026, 10, 28, 7, 57, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 15, 57, tzinfo=timezone(timedelta(hours=8))),
    ],
    ids=["naive", "utc", "plus-eight"],
)
async def test_times_are_written_in_utc_and_say_so(mock_db: MagicMock, moment: datetime) -> None:
    messages = [make_message("m1", "user", "Hello", created_at=moment)]

    html = await render_page(mock_db, "zh", chat=make_chat(created_at=moment), messages=messages)

    assert '<span class="time">2026-10-28 07:57 UTC</span>' in html
    assert '<span class="stat">2026-10-28 07:57 UTC</span>' in html
