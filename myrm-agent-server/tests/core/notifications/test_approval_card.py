"""Approval notification cards: what the owner reads, and which channels get buttons that actually work."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.channels.types.components import ActionButton, ButtonStyle
from app.core.notifications import approval_card
from app.core.notifications.approval_card import APPROVAL_CLICK_CHANNELS, build_approval_card

_NOW = datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return _NOW if tz is None else _NOW.astimezone(tz)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(approval_card, "datetime", _FrozenDatetime)


def _draft(*, expires_in_minutes: float | None = 5, **payload_overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "draft_content": "Your refund of $500 is approved.",
        "original_content": "Where is my refund?",
        "channel": "whatsapp",
        "recipient_id": "8613800000000@s.whatsapp.net",
        "original_sender_id": "8613800000000@s.whatsapp.net",
        "topic_id": "topic-1",
        "draft_timeout_action": "auto_reject",
        "outbound": {"content": "", "media": []},
    }
    payload.update(payload_overrides)
    return {
        "approval_id": "appr_123",
        "action_type": "outbound_draft",
        "status": "PENDING",
        "severity": "info",
        "reason": "AI-generated reply requires review before sending to channel.",
        "payload": payload,
        "chat_id": "chat-1",
        "expires_at": None if expires_in_minutes is None else (_NOW + timedelta(minutes=expires_in_minutes)).isoformat(),
    }


def _buttons(components: tuple[tuple[object, ...], ...]) -> tuple[ActionButton, ...]:
    return tuple(button for row in components for button in row if isinstance(button, ActionButton))


class TestOutboundDraftCard:
    def test_shows_what_the_owner_needs_to_decide(self) -> None:
        content, _ = build_approval_card(_draft(), "telegram", "en")

        assert "Reply awaiting your review" in content
        assert "> Where is my refund?" in content
        assert "> Your refund of $500 is approved." in content
        assert "If nobody decides within 5 min, the reply is discarded." in content

    def test_never_exposes_internal_identifiers(self) -> None:
        content, _ = build_approval_card(_draft(), "telegram", "en")

        for internal in ("outbound_draft", "appr_123", "topic-1", "auto_reject", "8613800000000", "chat-1"):
            assert internal not in content

    def test_an_automatically_sent_draft_says_so(self) -> None:
        content, _ = build_approval_card(_draft(draft_timeout_action="auto_send"), "telegram", "en")

        assert "the reply is sent automatically" in content
        assert "discarded" not in content

    def test_is_written_in_the_owners_language(self) -> None:
        content, components = build_approval_card(_draft(), "telegram", "zh-CN")

        assert "有一条回复等待你审核" in content
        assert "若 5 分钟内无人处理，该回复将被丢弃。" in content
        assert [button.label for button in _buttons(components)] == ["批准", "拒绝"]

    def test_every_line_of_a_multi_line_message_is_quoted(self) -> None:
        content, _ = build_approval_card(_draft(draft_content="Line one\n\nLine three"), "telegram", "en")

        assert "> Line one\n> \n> Line three" in content

    def test_long_texts_are_cut_so_the_card_fits_one_message(self) -> None:
        content, _ = build_approval_card(_draft(draft_content="r" * 5000, original_content="q" * 5000), "telegram", "en")

        assert "q" * 300 + "…" in content and "q" * 301 not in content
        assert "r" * 800 + "…" in content and "r" * 801 not in content

    def test_a_reply_with_only_attachments_has_no_empty_reply_section(self) -> None:
        outbound = {"media": [{"media_type": "document", "filename": "quote.pdf"}]}
        content, _ = build_approval_card(_draft(draft_content="", outbound=outbound), "telegram", "en")

        assert "Drafted reply" not in content
        assert "**Attachments:** quote.pdf" in content

    def test_attachment_names_never_include_urls(self) -> None:
        outbound = {
            "media": [
                {"media_type": "image", "path": "/tmp/work/shot.png"},
                {"media_type": "document", "filename": "quote.pdf", "path": "/tmp/work/ignored.bin"},
                {"media_type": "audio", "url": "https://files.example/a.mp3?token=secret"},
            ]
        }
        content, _ = build_approval_card(_draft(outbound=outbound), "telegram", "en")

        assert "**Attachments:** shot.png, quote.pdf, audio" in content
        assert "secret" not in content

    def test_many_attachments_are_abbreviated(self) -> None:
        outbound = {"media": [{"media_type": "image", "filename": f"{n}.png"} for n in range(7)]}
        content, _ = build_approval_card(_draft(outbound=outbound), "telegram", "en")

        assert "**Attachments:** 0.png, 1.png, 2.png, 3.png, 4.png, …" in content

    @pytest.mark.parametrize(("expires_in_minutes", "minutes"), [(5, 5), (0.5, 1), (-3, 1), (4.2, 5)])
    def test_remaining_time_is_rounded_up_and_never_below_one_minute(self, expires_in_minutes: float, minutes: int) -> None:
        content, _ = build_approval_card(_draft(expires_in_minutes=expires_in_minutes), "telegram", "en")

        assert f"within {minutes} min" in content

    def test_an_unknown_expiry_omits_the_deadline_line(self) -> None:
        content, _ = build_approval_card(_draft(expires_in_minutes=None), "telegram", "en")

        assert "If nobody decides" not in content

    def test_a_malformed_payload_still_produces_a_card(self) -> None:
        data = _draft()
        data["payload"] = "not-a-mapping"

        content, components = build_approval_card(data, "telegram", "en")

        assert content.startswith("✏️ **Reply awaiting your review**")
        assert len(_buttons(components)) == 2


class TestDecisionButtons:
    def test_telegram_gets_approve_and_deny_buttons_the_router_understands(self) -> None:
        _, components = build_approval_card(_draft(), "telegram", "en")

        approve, deny = _buttons(components)
        assert (approve.label, approve.action_id, approve.style) == ("Approve", "approval:approve:appr_123", ButtonStyle.PRIMARY)
        assert (deny.label, deny.action_id, deny.style) == ("Deny", "approval:deny:appr_123", ButtonStyle.DANGER)

    @pytest.mark.parametrize("channel", ["slack", "discord", "feishu", "whatsapp", "teams", "wecom", None])
    def test_channels_whose_clicks_are_not_handled_get_a_pointer_instead_of_dead_buttons(self, channel: str | None) -> None:
        content, components = build_approval_card(_draft(), channel, "en")

        assert components == ()
        assert content.endswith("Open the Myrm AI app to review and decide.")

    def test_only_telegram_clicks_are_handled(self) -> None:
        assert APPROVAL_CLICK_CHANNELS == frozenset({"telegram"})

    def test_a_card_without_an_approval_id_offers_no_buttons(self) -> None:
        data = _draft()
        data["approval_id"] = ""

        _, components = build_approval_card(data, "telegram", "en")

        assert components == ()


class TestGenericApprovalCard:
    DATA: dict[str, object] = {
        "approval_id": "appr_9",
        "action_type": "delete_database",
        "severity": "critical",
        "description": "Drop table users in prod",
    }

    def test_english_copy_is_unchanged(self) -> None:
        content, components = build_approval_card(self.DATA, "telegram", "en")

        assert content == "⚠️ **Approval Required: delete_database**\nSeverity: `critical`\n\n> Drop table users in prod"
        assert [button.action_id for button in _buttons(components)] == ["approval:approve:appr_9", "approval:deny:appr_9"]

    def test_other_channels_point_to_the_app(self) -> None:
        content, components = build_approval_card({**self.DATA, "description": ""}, "slack", "en")

        assert components == ()
        assert content == (
            "⚠️ **Approval Required: delete_database**\nSeverity: `critical`\n\nOpen the Myrm AI app to review and decide."
        )

    def test_is_localized_too(self) -> None:
        content, _ = build_approval_card(self.DATA, "telegram", "zh-CN")

        assert content.startswith("⚠️ **需要审批：delete_database**\n级别：`critical`")
