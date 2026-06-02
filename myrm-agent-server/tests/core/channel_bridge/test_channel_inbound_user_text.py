from __future__ import annotations

from app.channels.types import ContextEntry, InboundMessage, MediaAttachment, MediaType, ReplyContext
from app.core.channel_bridge.agent_executor.helpers import (
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
