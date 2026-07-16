from __future__ import annotations

from app.channels.types import ContextEntry, InboundMessage, MediaAttachment, MediaType, ReplyContext
from app.core.channel_bridge.agent_executor.helpers import (
    _format_forwarded_email_context,
    _format_reply_context,
    build_channel_inbound_query,
)


def test_build_channel_inbound_query_banner_local_ingress() -> None:
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="Ping",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={},
    )
    out = build_channel_inbound_query(msg)
    assert "[Inbound channel message]" in out
    assert "channel=telegram" in out
    assert "ingress=local_connector" in out
    assert out.endswith("Ping")


def test_build_channel_inbound_query_banner_control_plane_ingress() -> None:
    msg = InboundMessage(
        channel="feishu",
        sender_id="u1",
        content="hello",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={"trusted_inbound": "control_plane"},
    )
    out = build_channel_inbound_query(msg)
    assert "ingress=control_plane" in out


def test_build_channel_inbound_query_with_group_context() -> None:
    ctx = (ContextEntry(sender_id="other", content="prior note", timestamp=1.0),)
    msg = InboundMessage(
        channel="slack",
        sender_id="u1",
        content="follow up",
        sent_at=2.0,
        sent_timezone="UTC",
        chat_id="thread-1",
        user_id="u1",
        is_group=True,
        mentioned=False,
        context_messages=ctx,
        metadata={},
    )
    out = build_channel_inbound_query(msg)
    assert "[Inbound channel message]" in out
    assert "[Recent group chat messages for context]" in out
    assert "prior note" in out
    assert "follow up" in out


def test_build_channel_inbound_query_multimodal_with_images() -> None:
    """When image_data_list is present, returns OpenAI Vision-compatible list."""
    msg = InboundMessage(
        channel="discord",
        sender_id="u1",
        content="What is this?",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={
            "image_data_list": [
                {"data_url": "data:image/jpeg;base64,/9j/abc", "mime_type": "image/jpeg"},
            ]
        },
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]["type"] == "text"
    assert "What is this?" in out[0]["text"]
    assert out[1]["type"] == "image_url"
    assert out[1]["image_url"]["url"] == "data:image/jpeg;base64,/9j/abc"


def test_build_channel_inbound_query_multimodal_multiple_images() -> None:
    """Multiple images produce multiple image_url parts."""
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="Compare these",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={
            "image_data_list": [
                {"data_url": "data:image/png;base64,img1", "mime_type": "image/png"},
                {"data_url": "data:image/jpeg;base64,img2", "mime_type": "image/jpeg"},
            ]
        },
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, list)
    assert len(out) == 3
    assert out[0]["type"] == "text"
    image_parts = [p for p in out if p["type"] == "image_url"]
    assert len(image_parts) == 2


def test_build_channel_inbound_query_empty_image_list_returns_text() -> None:
    """Empty image_data_list falls back to plain text."""
    msg = InboundMessage(
        channel="feishu",
        sender_id="u1",
        content="No images",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={"image_data_list": []},
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "No images" in out


def test_build_channel_inbound_query_invalid_image_data_returns_text() -> None:
    """Malformed image_data_list entries are skipped; if all skip, returns text."""
    msg = InboundMessage(
        channel="slack",
        sender_id="u1",
        content="Bad data",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={"image_data_list": [{"no_data_url": True}]},
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "Bad data" in out


def test_build_channel_inbound_query_group_context_with_images() -> None:
    """Group context messages + images produces multimodal with context in text part."""
    ctx = (ContextEntry(sender_id="alice", content="look at this", timestamp=1.0),)
    msg = InboundMessage(
        channel="discord",
        sender_id="bob",
        content="What is in this photo?",
        sent_at=2.0,
        sent_timezone="UTC",
        chat_id="group-1",
        user_id="bob",
        is_group=True,
        mentioned=True,
        context_messages=ctx,
        metadata={
            "image_data_list": [
                {"data_url": "data:image/png;base64,abc123", "mime_type": "image/png"},
            ]
        },
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, list)
    text_part = out[0]
    assert text_part["type"] == "text"
    assert "[Recent group chat messages for context]" in text_part["text"]
    assert "look at this" in text_part["text"]
    assert "What is in this photo?" in text_part["text"]
    assert out[1]["type"] == "image_url"


def test_build_channel_inbound_query_non_list_image_data_returns_text() -> None:
    """When image_data_list is not a list, falls back to plain text."""
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="Corrupt data",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={"image_data_list": "not_a_list"},
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "Corrupt data" in out


# ---------- Reply Context Tests ----------


def test_format_reply_context_with_sender_name_and_content() -> None:
    reply = ReplyContext(message_id="m1", content="Hello world", sender_name="Alice")
    result = _format_reply_context(reply)
    assert "[Replying to Alice]" in result
    assert '"Hello world"' in result


def test_format_reply_context_falls_back_to_sender_id() -> None:
    reply = ReplyContext(message_id="m1", content="test", sender_id="user123")
    result = _format_reply_context(reply)
    assert "[Replying to user123]" in result


def test_format_reply_context_falls_back_to_someone() -> None:
    reply = ReplyContext(message_id="m1", content="test")
    result = _format_reply_context(reply)
    assert "[Replying to someone]" in result


def test_format_reply_context_truncates_long_content() -> None:
    long_text = "x" * 600
    reply = ReplyContext(message_id="m1", content=long_text, sender_name="Bob")
    result = _format_reply_context(reply)
    assert "..." in result
    assert len(result) < 700


def test_format_reply_context_with_media_hint() -> None:
    media = (
        MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg"),
        MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.com/f.pdf"),
    )
    reply = ReplyContext(message_id="m1", content="check this", sender_name="Carol", media=media)
    result = _format_reply_context(reply)
    assert "[2 attachment(s)]" in result


def test_format_reply_context_media_only_no_content() -> None:
    media = (MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/img.jpg"),)
    reply = ReplyContext(message_id="m1", content="", sender_name="Dave", media=media)
    result = _format_reply_context(reply)
    assert "[Replying to Dave]" in result
    assert "[1 attachment(s)]" in result
    assert '": "' not in result


def test_build_channel_inbound_query_with_reply_to() -> None:
    """reply_to is injected as a disambiguation prefix before the user's message."""
    reply = ReplyContext(message_id="m1", content="Tomorrow is sunny", sender_name="Myrm-Bot")
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="What about the day after?",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={},
        reply_to=reply,
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "[Replying to Myrm-Bot]" in out
    assert '"Tomorrow is sunny"' in out
    assert "---" in out
    assert "What about the day after?" in out
    # Reply prefix comes before user content
    reply_idx = out.index("[Replying to")
    user_idx = out.index("What about the day after?")
    assert reply_idx < user_idx


def test_build_channel_inbound_query_reply_to_none_unchanged() -> None:
    """When reply_to is None, output is identical to the base case."""
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="Simple message",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={},
        reply_to=None,
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "[Replying to" not in out
    assert out.endswith("Simple message")


def test_build_channel_inbound_query_reply_to_with_group_context() -> None:
    """reply_to + group context both appear in the correct order."""
    reply = ReplyContext(message_id="m1", content="meeting cancelled", sender_name="Manager")
    ctx = (ContextEntry(sender_id="coworker", content="got it", timestamp=1.0),)
    msg = InboundMessage(
        channel="feishu",
        sender_id="u1",
        content="update my calendar",
        sent_at=2.0,
        sent_timezone="UTC",
        chat_id="group-1",
        user_id="u1",
        is_group=True,
        mentioned=True,
        context_messages=ctx,
        metadata={},
        reply_to=reply,
    )
    out = build_channel_inbound_query(msg)
    assert "[Replying to Manager]" in out
    assert '"meeting cancelled"' in out
    assert "[Recent group chat messages for context]" in out
    assert "update my calendar" in out


def test_build_channel_inbound_query_reply_to_with_images() -> None:
    """reply_to + multimodal (images) produces correct multimodal output."""
    reply = ReplyContext(message_id="m1", content="see this chart", sender_name="Analyst")
    msg = InboundMessage(
        channel="discord",
        sender_id="u1",
        content="Explain this",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={"image_data_list": [{"data_url": "data:image/png;base64,abc", "mime_type": "image/png"}]},
        reply_to=reply,
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, list)
    text_part = out[0]["text"]
    assert "[Replying to Analyst]" in text_part
    assert '"see this chart"' in text_part
    assert "Explain this" in text_part


# ---------- Group Context sender_name Tests ----------


def test_group_context_uses_sender_name_when_available() -> None:
    """When sender_name is set, context formatting uses it instead of sender_id."""
    ctx = (ContextEntry(sender_id="ou_xxxx", content="use Redis", timestamp=1.0, sender_name="Alice"),)
    msg = InboundMessage(
        channel="feishu",
        sender_id="u1",
        content="what do you think?",
        sent_at=2.0,
        sent_timezone="UTC",
        chat_id="group-1",
        user_id="u1",
        is_group=True,
        mentioned=True,
        context_messages=ctx,
        metadata={},
    )
    out = build_channel_inbound_query(msg)
    assert "Alice: " in out
    assert "ou_xxxx" not in out


def test_group_context_falls_back_to_sender_id() -> None:
    """When sender_name is None, falls back to sender_id."""
    ctx = (ContextEntry(sender_id="U0ABC", content="hello", timestamp=1.0),)
    msg = InboundMessage(
        channel="slack",
        sender_id="u1",
        content="reply",
        sent_at=2.0,
        sent_timezone="UTC",
        chat_id="group-2",
        user_id="u1",
        is_group=True,
        mentioned=True,
        context_messages=ctx,
        metadata={},
    )
    out = build_channel_inbound_query(msg)
    assert "U0ABC: " in out


def test_group_context_empty_sender_name_falls_back() -> None:
    """Empty string sender_name falls back to sender_id (falsy in Python)."""
    ctx = (ContextEntry(sender_id="U999", content="test", timestamp=1.0, sender_name=""),)
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        content="go",
        sent_at=2.0,
        sent_timezone="UTC",
        chat_id="group-3",
        user_id="u1",
        is_group=True,
        mentioned=True,
        context_messages=ctx,
        metadata={},
    )
    out = build_channel_inbound_query(msg)
    assert "U999: " in out
    assert ": test" in out


def test_group_context_mixed_sender_names() -> None:
    """Mixed: some entries have sender_name, some don't."""
    ctx = (
        ContextEntry(sender_id="ou_aaa", content="idea A", timestamp=1.0, sender_name="Alice"),
        ContextEntry(sender_id="ou_bbb", content="idea B", timestamp=2.0),
        ContextEntry(sender_id="ou_ccc", content="idea C", timestamp=3.0, sender_name="Charlie"),
    )
    msg = InboundMessage(
        channel="feishu",
        sender_id="u1",
        content="summarize",
        sent_at=4.0,
        sent_timezone="UTC",
        chat_id="group-4",
        user_id="u1",
        is_group=True,
        mentioned=True,
        context_messages=ctx,
        metadata={},
    )
    out = build_channel_inbound_query(msg)
    assert "Alice: " in out
    assert "ou_bbb: " in out
    assert "Charlie: " in out
    assert "ou_aaa" not in out
    assert "ou_ccc" not in out


# ---------- Forwarded Email Context Tests ----------


def test_format_forwarded_email_context_full_metadata() -> None:
    """All forwarded fields are rendered in the context block."""
    meta: dict[str, object] = {
        "is_forwarded": True,
        "forwarded_from": "finance@company.com",
        "forwarded_subject": "Invoice #12345",
        "forwarded_date": "Mon, 14 Jul 2026 10:00:00 +0800",
        "forwarded_body": "Please pay $500 by end of month.",
    }
    result = _format_forwarded_email_context(meta, "Expense this")
    assert "[Forwarded Email]" in result
    assert "From: finance@company.com" in result
    assert "Subject: Invoice #12345" in result
    assert "Date: Mon, 14 Jul 2026 10:00:00 +0800" in result
    assert "Please pay $500 by end of month." in result


def test_format_forwarded_email_context_body_only() -> None:
    """When only forwarded_body is present, still renders block."""
    meta: dict[str, object] = {
        "is_forwarded": True,
        "forwarded_body": "Meeting at 3pm tomorrow.",
    }
    result = _format_forwarded_email_context(meta, "Summarize this")
    assert "[Forwarded Email]" in result
    assert "Meeting at 3pm tomorrow." in result
    assert "From:" not in result


def test_format_forwarded_email_context_empty_returns_empty() -> None:
    """No forwarded fields yields empty string (no noise injected)."""
    meta: dict[str, object] = {"is_forwarded": True}
    result = _format_forwarded_email_context(meta, "Some content")
    assert result == ""


def test_format_forwarded_email_context_truncates_long_body() -> None:
    """Bodies exceeding _FWD_BODY_MAX_LEN are truncated with ellipsis."""
    long_body = "x" * 6000
    meta: dict[str, object] = {
        "is_forwarded": True,
        "forwarded_from": "sender@test.com",
        "forwarded_body": long_body,
    }
    result = _format_forwarded_email_context(meta, "Summarize")
    assert "..." in result
    assert len(result) < 6000


def test_format_forwarded_email_context_partial_headers() -> None:
    """Only available headers are included; missing ones are skipped."""
    meta: dict[str, object] = {
        "is_forwarded": True,
        "forwarded_subject": "Important notice",
        "forwarded_body": "Please review the attached document.",
    }
    result = _format_forwarded_email_context(meta, "Review this")
    assert "[Forwarded Email]" in result
    assert "Subject: Important notice" in result
    assert "From:" not in result
    assert "Date:" not in result
    assert "review the attached" in result


def test_format_forwarded_email_context_no_dup_when_content_equals_body() -> None:
    """When user_content == forwarded_body (pure forward), body is NOT duplicated."""
    body_text = "Meeting at 3pm tomorrow."
    meta: dict[str, object] = {
        "is_forwarded": True,
        "forwarded_from": "hr@company.com",
        "forwarded_body": body_text,
    }
    result = _format_forwarded_email_context(meta, body_text)
    assert "[Forwarded Email]" in result
    assert "From: hr@company.com" in result
    assert body_text not in result


def test_build_channel_inbound_query_forwarded_with_annotation() -> None:
    """Forwarded email with user annotation: both annotation and forwarded body appear."""
    msg = InboundMessage(
        channel="email",
        sender_id="user@example.com",
        content="Please reimburse this",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="user@example.com",
        user_id="user@example.com",
        is_group=False,
        mentioned=True,
        metadata={
            "is_forwarded": True,
            "forwarded_from": "vendor@shop.com",
            "forwarded_subject": "Receipt #789",
            "forwarded_body": "Total: $42.00\nItem: Office supplies",
        },
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "Please reimburse this" in out
    assert "[Forwarded Email]" in out
    assert "From: vendor@shop.com" in out
    assert "Subject: Receipt #789" in out
    assert "Total: $42.00" in out


def test_build_channel_inbound_query_forwarded_with_annotation_zh() -> None:
    """Forwarded email with Chinese annotation includes both annotation and original."""
    msg = InboundMessage(
        channel="email",
        sender_id="user@example.com",
        content="帮我报销这个",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="user@example.com",
        user_id="user@example.com",
        is_group=False,
        mentioned=True,
        metadata={
            "is_forwarded": True,
            "forwarded_from": "finance@company.com",
            "forwarded_subject": "Invoice #12345",
            "forwarded_date": "2026-07-10",
            "forwarded_body": "Dear Customer,\nYour invoice for $5,000 is attached.",
        },
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "帮我报销这个" in out
    assert "[Forwarded Email]" in out
    assert "From: finance@company.com" in out
    assert "Subject: Invoice #12345" in out
    assert "Date: 2026-07-10" in out
    assert "invoice for" in out


def test_build_channel_inbound_query_forwarded_no_annotation() -> None:
    """Pure forward (no annotation): headers injected but body NOT duplicated."""
    fwd_text = "Team outing is scheduled for July 20."
    msg = InboundMessage(
        channel="email",
        sender_id="user@example.com",
        content=fwd_text,
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="user@example.com",
        user_id="user@example.com",
        is_group=False,
        mentioned=True,
        metadata={
            "is_forwarded": True,
            "forwarded_from": "hr@company.com",
            "forwarded_subject": "Team outing schedule",
            "forwarded_body": fwd_text,
        },
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "[Forwarded Email]" in out
    assert "From: hr@company.com" in out
    assert out.count(fwd_text) == 1


def test_build_channel_inbound_query_forwarded_without_body() -> None:
    """Forwarded flag set but no forwarded_body: no forwarded block injected."""
    msg = InboundMessage(
        channel="email",
        sender_id="user@example.com",
        content="Check this",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="user@example.com",
        user_id="user@example.com",
        is_group=False,
        mentioned=True,
        metadata={"is_forwarded": True},
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "Check this" in out
    assert "[Forwarded Email]" not in out


def test_build_channel_inbound_query_not_forwarded_no_injection() -> None:
    """Non-forwarded email: no forwarded context injected even if metadata has fields."""
    msg = InboundMessage(
        channel="email",
        sender_id="user@example.com",
        content="Normal email",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="user@example.com",
        user_id="user@example.com",
        is_group=False,
        mentioned=True,
        metadata={"forwarded_body": "should not appear"},
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, str)
    assert "Normal email" in out
    assert "[Forwarded Email]" not in out
    assert "should not appear" not in out


def test_build_channel_inbound_query_forwarded_with_images() -> None:
    """Forwarded email + images produces multimodal output with forwarded context."""
    msg = InboundMessage(
        channel="email",
        sender_id="user@example.com",
        content="翻译成英文",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="user@example.com",
        user_id="user@example.com",
        is_group=False,
        mentioned=True,
        metadata={
            "is_forwarded": True,
            "forwarded_from": "wang@example.cn",
            "forwarded_subject": "项目进度报告",
            "forwarded_body": "本月项目完成率达到85%",
            "image_data_list": [
                {"data_url": "data:image/png;base64,abc123", "mime_type": "image/png"},
            ],
        },
    )
    out = build_channel_inbound_query(msg)
    assert isinstance(out, list)
    text_part = out[0]["text"]
    assert "翻译成英文" in text_part
    assert "[Forwarded Email]" in text_part
    assert "项目进度报告" in text_part
    assert "85%" in text_part
