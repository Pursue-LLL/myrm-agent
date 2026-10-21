"""Unit tests for Telegram inbound entity mention detection and mention stripping."""

from __future__ import annotations

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.models import TgChat, TgEntity, TgMessage, TgUser
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN


def _channel() -> TelegramChannel:
    ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    ch._bot_username = "testbot"
    ch._tg_bot_id = 123456789
    return ch


def _entity(entity_type: str, *, offset: int, length: int, user: TgUser | None = None) -> TgEntity:
    return TgEntity(type=entity_type, offset=offset, length=length, user=user)


class TestMessageMentionsBot:
    def test_returns_false_without_bot_username(self) -> None:
        ch = _channel()
        ch._bot_username = None
        msg = TgMessage(text="@testbot hi", entities=[_entity("mention", offset=0, length=8)])
        assert ch._message_mentions_bot(msg) is False

    def test_skips_invalid_mention_entity_bounds(self) -> None:
        ch = _channel()
        msg = TgMessage(
            text="@testbot hi",
            entities=[_entity("mention", offset=-1, length=8)],
        )
        assert ch._message_mentions_bot(msg) is False

    def test_ignores_wrong_mention_target(self) -> None:
        ch = _channel()
        msg = TgMessage(
            text="@otherbot hi",
            entities=[_entity("mention", offset=0, length=9)],
        )
        assert ch._message_mentions_bot(msg) is False

    def test_bot_command_without_at_suffix_is_ignored(self) -> None:
        ch = _channel()
        msg = TgMessage(
            text="/status",
            entities=[_entity("bot_command", offset=0, length=7)],
        )
        assert ch._message_mentions_bot(msg) is False

    def test_bot_command_with_invalid_bounds_is_ignored(self) -> None:
        ch = _channel()
        msg = TgMessage(
            text="/status@testbot",
            entities=[_entity("bot_command", offset=0, length=0)],
        )
        assert ch._message_mentions_bot(msg) is False

    def test_text_mention_matches_bot_id(self) -> None:
        ch = _channel()
        msg = TgMessage(
            text="hey bot",
            entities=[
                _entity(
                    "text_mention",
                    offset=0,
                    length=3,
                    user=TgUser(id=123456789),
                ),
            ],
        )
        assert ch._message_mentions_bot(msg) is True


class TestStripBotMentionText:
    def test_returns_original_when_username_missing(self) -> None:
        ch = _channel()
        ch._bot_username = None
        assert ch._strip_bot_mention_text("@testbot hi") == "@testbot hi"

    def test_strips_mention_with_trailing_punctuation(self) -> None:
        ch = _channel()
        assert ch._strip_bot_mention_text("@testbot, hello") == "hello"

    def test_preserves_text_when_strip_would_empty(self) -> None:
        ch = _channel()
        assert ch._strip_bot_mention_text("@testbot") == "@testbot"


class TestReplyToBotImplicitMention:
    """R1b: reply-to-bot counts as implicit mention only for human senders.

    Another bot replying to our message must not wake the agent; bots can
    still trigger via explicit @mention (covered by TestMessageMentionsBot).
    """

    @staticmethod
    def _reply_msg(sender_is_bot: bool) -> TgMessage:
        chat = TgChat(id=-100, type="supergroup", title="G")
        # TgMessage.from_user has alias "from" and the model is not
        # populate-by-name, so the field must be set through the alias.
        return TgMessage(
            message_id=10,
            text="ping",
            chat=chat,
            **{"from": TgUser(id=222, is_bot=sender_is_bot)},
            reply_to_message=TgMessage(
                message_id=9,
                text="agent reply",
                chat=chat,
                **{"from": TgUser(id=123456789)},  # our bot
            ),
        )

    def test_human_reply_to_bot_gets_implicit_mention(self) -> None:
        ch = _channel()
        inbound = ch._parse_message_model(self._reply_msg(sender_is_bot=False), is_edit=False)
        assert inbound is not None
        assert inbound.mentioned is True
        assert inbound.is_bot is False

    def test_bot_reply_to_bot_gets_no_implicit_mention(self) -> None:
        ch = _channel()
        inbound = ch._parse_message_model(self._reply_msg(sender_is_bot=True), is_edit=False)
        assert inbound is not None
        assert inbound.mentioned is False
        assert inbound.is_bot is True
