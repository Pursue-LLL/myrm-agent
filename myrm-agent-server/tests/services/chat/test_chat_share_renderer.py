"""Tests for chat share HTML renderer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.security.share.share_locale import ShareLang
from app.database.dto import ChatDTO, MessageDTO
from app.services.chat.share_renderer import render_share_html


def _make_chat(chat_id: str = "chat-1") -> ChatDTO:
    now = datetime.now(timezone.utc)
    return ChatDTO(
        id=chat_id,
        agent_id="agent-1",
        title="My Test Chat",
        first_message="Hello world",
        created_at=now,
        updated_at=now,
    )


def _make_messages() -> list[MessageDTO]:
    now = datetime.now(timezone.utc)
    return [
        MessageDTO(
            id="m1",
            chat_id="chat-1",
            role="user",
            content="Hello",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="m2",
            chat_id="chat-1",
            role="assistant",
            content="Hi there!",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="m3",
            chat_id="chat-1",
            role="system",
            content="System prompt",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
    ]


@pytest.fixture
def mock_db():
    db = MagicMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)
    return db


async def test_render_share_html_basic(mock_db) -> None:
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=_make_messages(),
        ),
    ):
        html = await render_share_html("chat-1", mock_db, lang="en")
        assert html is not None
        assert "My Test Chat" in html
        assert "Hello" in html
        assert "Hi there!" in html
        assert "System prompt" not in html
        assert "<!DOCTYPE html>" in html
        assert "og:title" in html


async def test_render_share_html_chat_not_found(mock_db) -> None:
    with patch(
        "app.services.chat.share_renderer.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
        return_value=None,
    ):
        html = await render_share_html("nonexistent", mock_db, lang="en")
        assert html is None


async def test_render_share_html_escapes_xss(mock_db) -> None:
    now = datetime.now(timezone.utc)
    xss_messages = [
        MessageDTO(
            id="m1",
            chat_id="chat-1",
            role="user",
            content='<script>alert("xss")</script>',
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="m2",
            chat_id="chat-1",
            role="assistant",
            content="<img onerror=alert(1) src=x> and **bold**",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
    ]
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=xss_messages,
        ),
    ):
        html = await render_share_html("chat-1", mock_db, lang="en")
        assert html is not None
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "<img" not in html
        assert "<strong>bold</strong>" in html


async def test_render_message_markdown(mock_db) -> None:
    """Assistant messages are rendered as Markdown; user messages are plain text."""
    now = datetime.now(timezone.utc)
    messages = [
        MessageDTO(
            id="m1",
            chat_id="chat-1",
            role="user",
            content="**not bold** `not code`",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
        MessageDTO(
            id="m2",
            chat_id="chat-1",
            role="assistant",
            content="**bold** and `code`\n\n```python\nprint(1)\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |",
            sent_at=now,
            sent_timezone="UTC",
            created_at=now,
        ),
    ]
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=messages,
        ),
    ):
        html = await render_share_html("chat-1", mock_db, lang="en")
        assert html is not None
        # Assistant: Markdown rendered
        assert "<strong>bold</strong>" in html
        assert "<code>code</code>" in html
        assert '<code class="language-python">' in html
        assert "<table>" in html
        # User: plain text, no Markdown rendering
        assert "**not bold**" in html
        assert "<strong>not bold</strong>" not in html


async def test_render_html_includes_dark_mode(mock_db) -> None:
    """Generated HTML includes dark mode CSS."""
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=_make_messages(),
        ),
    ):
        html = await render_share_html("chat-1", mock_db, lang="en")
        assert html is not None
        assert "prefers-color-scheme:dark" in html
        assert "background:#111827" in html


async def test_render_share_html_with_agent_model_selection() -> None:
    """Agent with model_selection renders model name in identity card."""
    from app.database.models.agent import Agent

    mock_agent = MagicMock(spec=Agent)
    mock_agent.name = "Code Developer"
    mock_agent.description = "Focused coding assistant"
    mock_agent.model_selection = {"model": "gpt-4o", "provider": "openai"}

    db = MagicMock()
    agent_result = MagicMock()
    agent_result.scalars.return_value.first.return_value = mock_agent
    db.execute = AsyncMock(return_value=agent_result)

    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=_make_messages(),
        ),
    ):
        html = await render_share_html("chat-1", db, lang="en")
        assert html is not None
        assert "Code Developer" in html
        assert "gpt-4o" in html


async def test_a_parked_paste_reads_as_its_opening_and_size_on_the_shared_page(mock_db) -> None:
    """The stored stub names a file of the owner's workspace; a visitor of the page must not see it."""
    now = datetime.now(timezone.utc)
    stub = '<file_spillover path=".myrm/pastes/payload_1.md" chars="41200"><preview_start>x</preview_start></file_spillover>'
    parked = MessageDTO(
        id="m1",
        chat_id="chat-1",
        role="user",
        content=stub,
        extra_data={
            "spillover": {
                "spillover_path": ".myrm/pastes/payload_1.md",
                "original_char_count": 41_200,
                "preview": "meeting-line: the decision",
            }
        },
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
    )
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata", new_callable=AsyncMock, return_value=_make_chat()
        ),
        patch("app.services.chat.share_renderer.ChatService.get_all_messages", new_callable=AsyncMock, return_value=[parked]),
    ):
        html = await render_share_html("chat-1", mock_db, lang="en")

    assert html is not None
    assert "meeting-line: the decision" in html
    assert "41,200 characters" in html
    assert "file_spillover" not in html
    assert ".myrm" not in html


async def test_the_systems_notes_about_settled_background_tasks_are_not_on_the_shared_page(mock_db) -> None:
    now = datetime.now(timezone.utc)
    note = MessageDTO(
        id="wakeup_followup_t1",
        chat_id="chat-1",
        role="user",
        content="<system_notification type='adaptive_wakeup_followup'>job done</system_notification>",
        extra_data={"wakeup_notice": "followup"},
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
    )
    typed = MessageDTO(
        id="m1", chat_id="chat-1", role="user", content="what the user typed", sent_at=now, sent_timezone="UTC", created_at=now
    )
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata", new_callable=AsyncMock, return_value=_make_chat()
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages", new_callable=AsyncMock, return_value=[typed, note]
        ),
    ):
        html = await render_share_html("chat-1", mock_db, lang="en")

    assert html is not None
    assert "what the user typed" in html
    assert "adaptive_wakeup_followup" not in html
    assert "system_notification" not in html


def _user_message(content: str) -> MessageDTO:
    now = datetime.now(timezone.utc)
    return MessageDTO(id="m1", chat_id="chat-1", role="user", content=content, sent_at=now, sent_timezone="UTC", created_at=now)


async def _render(
    db: MagicMock, lang: ShareLang, *, chat: ChatDTO | None = None, messages: list[MessageDTO] | None = None
) -> str:
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=chat or _make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=messages if messages is not None else _make_messages(),
        ),
    ):
        html = await render_share_html("chat-1", db, lang=lang)
    assert html is not None
    return html


@pytest.mark.parametrize(
    ("lang", "html_lang", "you", "assistant", "count", "brand", "foreign"),
    [
        ("en", "en", "You", "Assistant", "2 messages", "Shared via Myrm Agent", ("你<", "助手<", "条消息", "由 Myrm Agent 分享")),
        ("zh", "zh-CN", "你", "助手", "2 条消息", "由 Myrm Agent 分享", (">You<", ">Assistant<", "messages<", "Shared via")),
    ],
)
async def test_the_page_chrome_is_written_in_the_visitor_language(
    mock_db, lang: ShareLang, html_lang: str, you: str, assistant: str, count: str, brand: str, foreign: tuple[str, ...]
) -> None:
    html = await _render(mock_db, lang)

    assert f'<html lang="{html_lang}">' in html
    assert f'<span class="role">{you}</span>' in html
    assert f'<span class="role">{assistant}</span>' in html
    assert f'<span class="stat">{count}</span>' in html
    assert f"<p>{brand}</p>" in html
    for fragment in foreign:
        assert fragment not in html


async def test_the_conversation_itself_is_not_translated(mock_db) -> None:
    html = await _render(mock_db, "zh")

    assert "My Test Chat" in html
    assert "Hi there!" in html


@pytest.mark.parametrize(
    ("lang", "expected"),
    [("en", '<span class="stat">1 message</span>'), ("zh", '<span class="stat">1 条消息</span>')],
)
async def test_a_single_message_is_counted_in_the_singular(mock_db, lang: ShareLang, expected: str) -> None:
    html = await _render(mock_db, lang, messages=[_user_message("Hello")])

    assert expected in html
    assert "1 messages" not in html


@pytest.mark.parametrize(
    ("lang", "title", "agent"),
    [("en", "Shared Conversation", "Default Agent"), ("zh", "分享的对话", "默认智能体")],
)
async def test_an_untitled_chat_without_agent_falls_back_in_the_visitor_language(
    mock_db, lang: ShareLang, title: str, agent: str
) -> None:
    chat = _make_chat().model_copy(update={"title": None, "agent_id": None})

    html = await _render(mock_db, lang, chat=chat)

    assert f"<title>{title}</title>" in html
    assert f'<div class="agent-name">{agent}</div>' in html


@pytest.mark.parametrize(("lang", "expected"), [("en", "Agent"), ("zh", "智能体")])
async def test_a_deleted_agent_falls_back_in_the_visitor_language(mock_db, lang: ShareLang, expected: str) -> None:
    html = await _render(mock_db, lang)

    assert f'<div class="agent-name">{expected}</div>' in html


async def test_the_name_an_owner_gave_the_agent_is_shown_as_is_in_every_language() -> None:
    from app.database.models.agent import Agent

    agent = MagicMock(spec=Agent)
    agent.name = "Code Developer"
    agent.description = ""
    agent.model_selection = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(first=MagicMock(return_value=agent)))))

    html = await _render(db, "zh")

    assert '<div class="agent-name">Code Developer</div>' in html
