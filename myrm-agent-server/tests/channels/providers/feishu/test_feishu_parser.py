"""Tests for Feishu inbound message parser — rich text, mentions, media."""

from __future__ import annotations

import json

from app.channels.providers.feishu.parser import (
    CardParseResult,
    PostParseResult,
    parse_inbound_event,
    parse_interactive_card,
    parse_post_content,
)


class TestParsePostContent:
    def test_simple_text_paragraphs(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "title": "Title",
                    "content": [
                        [{"tag": "text", "text": "Hello "}, {"tag": "text", "text": "World"}],
                        [{"tag": "text", "text": "Line 2"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert isinstance(result, PostParseResult)
        assert "Title" in result.text
        assert "Hello" in result.text
        assert "World" in result.text
        assert "Line 2" in result.text

    def test_bold_italic_strikethrough(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [
                            {"tag": "text", "text": "bold", "style": {"bold": True}},
                            {"tag": "text", "text": "italic", "style": {"italic": True}},
                            {"tag": "text", "text": "strike", "style": {"strikethrough": True}},
                        ],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "**bold**" in result.text
        assert "*italic*" in result.text
        assert "~~strike~~" in result.text

    def test_inline_code(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "text", "text": "foo()", "style": {"code": True}}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "`foo()`" in result.text

    def test_link_element(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "a", "text": "Click", "href": "https://example.com"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "[Click]" in result.text
        assert "https://example.com" in result.text

    def test_at_mention(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "at", "open_id": "ou_user1", "user_name": "Alice"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "@Alice" in result.text
        assert "ou_user1" in result.mentioned_open_ids

    def test_image_extraction(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "img", "image_key": "img_key_abc"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "img_key_abc" in result.image_keys

    def test_media_extraction(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "media", "file_key": "file_key_xyz", "file_name": "doc.pdf"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert ("file_key_xyz", "doc.pdf") in result.media_keys

    def test_code_block(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "code_block", "language": "python", "text": "print('hi')"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "```python" in result.text
        assert "print('hi')" in result.text

    def test_invalid_json_returns_fallback(self) -> None:
        result = parse_post_content("not json")
        assert result.text == "[富文本消息]"

    def test_empty_content_returns_fallback(self) -> None:
        result = parse_post_content(json.dumps({"zh_cn": {"content": []}}))
        assert result.text == "[富文本消息]"

    def test_direct_format(self) -> None:
        content = json.dumps(
            {
                "title": "Direct",
                "content": [[{"tag": "text", "text": "direct text"}]],
            }
        )
        result = parse_post_content(content)
        assert "Direct" in result.text
        assert "direct text" in result.text

    def test_en_us_locale(self) -> None:
        content = json.dumps(
            {
                "en_us": {
                    "title": "English",
                    "content": [[{"tag": "text", "text": "hello"}]],
                },
            }
        )
        result = parse_post_content(content)
        assert "English" in result.text

    def test_hr_element(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "text", "text": "before"}],
                        [{"tag": "hr"}],
                        [{"tag": "text", "text": "after"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "---" in result.text

    def test_emotion_element(self) -> None:
        content = json.dumps(
            {
                "zh_cn": {
                    "content": [
                        [{"tag": "emotion", "emoji_type": "SMILE"}],
                    ],
                },
            }
        )
        result = parse_post_content(content)
        assert "SMILE" in result.text


class TestParseInboundEvent:
    def _make_event(
        self,
        *,
        sender_id: str = "ou_user",
        msg_type: str = "text",
        content: str = '{"text": "hello"}',
        chat_type: str = "p2p",
        chat_id: str = "oc_chat",
        message_id: str = "om_msg",
        mentions: list[dict[str, object]] | None = None,
        root_id: str | None = None,
    ) -> dict[str, object]:
        msg: dict[str, object] = {
            "message_id": message_id,
            "message_type": msg_type,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "content": content,
        }
        if mentions is not None:
            msg["mentions"] = mentions
        if root_id is not None:
            msg["root_id"] = root_id

        return {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": sender_id}},
                "message": msg,
            },
        }

    def test_text_message(self) -> None:
        event = self._make_event()
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert result.content == "hello"
        assert result.sender_id == "ou_user"
        assert result.chat_id == "oc_chat"
        assert result.is_group is False

    def test_group_message_strips_at_placeholder(self) -> None:
        event = self._make_event(
            chat_type="group",
            content='{"text": "@_user_1 help me"}',
        )
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert "@_user_1" not in result.content
        assert "help me" in result.content

    def test_bot_mention_detection(self) -> None:
        event = self._make_event(
            chat_type="group",
            mentions=[{"id": {"open_id": "ou_bot"}, "key": "@_user_1"}],
        )
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert result.bot_mentioned is True

    def test_image_message(self) -> None:
        event = self._make_event(
            msg_type="image",
            content='{"image_key": "img_abc"}',
        )
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert "img_abc" in result.image_keys
        assert result.content == "[image]"

    def test_file_message(self) -> None:
        event = self._make_event(
            msg_type="file",
            content='{"file_key": "file_xyz", "file_name": "doc.pdf"}',
        )
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert ("file_xyz", "doc.pdf") in result.media_keys

    def test_audio_message(self) -> None:
        event = self._make_event(msg_type="audio", content='{"file_key": "audio_k"}')
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert result.content == "[audio]"

    def test_post_message(self) -> None:
        post = json.dumps(
            {
                "zh_cn": {
                    "content": [[{"tag": "text", "text": "rich text"}]],
                },
            }
        )
        event = self._make_event(msg_type="post", content=post)
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert "rich text" in result.content

    def test_empty_text_returns_none(self) -> None:
        event = self._make_event(content='{"text": "   "}')
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is None

    def test_thread_reply(self) -> None:
        event = self._make_event(root_id="om_root")
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert result.root_id == "om_root"

    def test_missing_sender_returns_none(self) -> None:
        event: dict[str, object] = {
            "header": {"event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {}},
                "message": {
                    "message_id": "om_1",
                    "message_type": "text",
                    "chat_id": "oc_1",
                    "chat_type": "p2p",
                    "content": '{"text": "hi"}',
                },
            },
        }
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is None

    def test_missing_event_returns_none(self) -> None:
        result = parse_inbound_event({"header": {}}, bot_open_id="ou_bot")
        assert result is None

    def test_unknown_msg_type(self) -> None:
        event = self._make_event(msg_type="sticker", content="{}")
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert result.content == "[sticker]"

    def test_share_chat_type(self) -> None:
        event = self._make_event(msg_type="share_chat", content="{}")
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert result.content == "[share_chat]"

    def test_interactive_card_message(self) -> None:
        card = json.dumps(
            {
                "header": {"title": {"tag": "plain_text", "content": "Notification"}},
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "Hello from card"}},
                    {"tag": "img", "img_key": "img_card_123", "alt": {"content": "photo"}},
                ],
            }
        )
        event = self._make_event(msg_type="interactive", content=card)
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert "Notification" in result.content
        assert "Hello from card" in result.content
        assert "img_card_123" in result.image_keys

    def test_interactive_card_empty_fallback(self) -> None:
        event = self._make_event(msg_type="interactive", content="{}")
        result = parse_inbound_event(event, bot_open_id="ou_bot")
        assert result is not None
        assert result.content == "[interactive]"


class TestParseInteractiveCard:
    def test_simple_card_with_header_and_text(self) -> None:
        card = json.dumps(
            {
                "header": {"title": {"tag": "plain_text", "content": "My Title"}},
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "Body text"}},
                ],
            }
        )
        result = parse_interactive_card(card)
        assert isinstance(result, CardParseResult)
        assert "My Title" in result.text
        assert "Body text" in result.text

    def test_card_with_image_keys(self) -> None:
        card = json.dumps(
            {
                "elements": [
                    {"tag": "img", "img_key": "key_abc", "alt": {"content": "A photo"}},
                    {"tag": "div", "text": {"tag": "plain_text", "content": "Some text"}},
                ],
            }
        )
        result = parse_interactive_card(card)
        assert "key_abc" in result.image_keys
        assert "A photo" in result.text
        assert "Some text" in result.text

    def test_card_with_nested_columns(self) -> None:
        card = json.dumps(
            {
                "elements": [
                    {
                        "tag": "column_set",
                        "columns": [
                            {
                                "tag": "column",
                                "elements": [
                                    {"tag": "div", "text": {"tag": "lark_md", "content": "Col 1"}},
                                ],
                            },
                            {
                                "tag": "column",
                                "elements": [
                                    {"tag": "div", "text": {"tag": "lark_md", "content": "Col 2"}},
                                ],
                            },
                        ],
                    },
                ],
            }
        )
        result = parse_interactive_card(card)
        assert "Col 1" in result.text
        assert "Col 2" in result.text

    def test_card_with_actions(self) -> None:
        card = json.dumps(
            {
                "elements": [
                    {
                        "tag": "action",
                        "actions": [
                            {"tag": "button", "text": {"tag": "plain_text", "content": "Approve"}},
                            {"tag": "button", "text": {"tag": "plain_text", "content": "Reject"}},
                        ],
                    },
                ],
            }
        )
        result = parse_interactive_card(card)
        assert "Approve" in result.text
        assert "Reject" in result.text

    def test_card_with_image_key_variant(self) -> None:
        card = json.dumps(
            {
                "elements": [
                    {"tag": "img", "image_key": "key_variant"},
                ],
            }
        )
        result = parse_interactive_card(card)
        assert "key_variant" in result.image_keys

    def test_card_deduplicates_text(self) -> None:
        card = json.dumps(
            {
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": "Same text"}},
                    {"tag": "div", "text": {"tag": "lark_md", "content": "Same text"}},
                    {"tag": "div", "text": {"tag": "lark_md", "content": "Different"}},
                ],
            }
        )
        result = parse_interactive_card(card)
        assert result.text.count("Same text") == 1
        assert "Different" in result.text

    def test_invalid_json_returns_fallback(self) -> None:
        result = parse_interactive_card("not json")
        assert result.text == "[interactive]"
        assert result.image_keys == []

    def test_non_dict_returns_fallback(self) -> None:
        result = parse_interactive_card(json.dumps([1, 2, 3]))
        assert result.text == "[interactive]"

    def test_empty_card_returns_fallback(self) -> None:
        result = parse_interactive_card(json.dumps({}))
        assert result.text == "[interactive]"

    def test_header_string_title(self) -> None:
        card = json.dumps(
            {
                "header": {"title": "Plain Title"},
                "elements": [],
            }
        )
        result = parse_interactive_card(card)
        assert "Plain Title" in result.text

    def test_body_field_extraction(self) -> None:
        card = json.dumps(
            {
                "body": {
                    "elements": [
                        {"tag": "div", "text": {"tag": "lark_md", "content": "From body"}},
                    ],
                },
            }
        )
        result = parse_interactive_card(card)
        assert "From body" in result.text
