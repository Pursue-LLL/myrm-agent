"""Member-safe wording for failed channel turns: one localized sentence per error kind plus a reference id."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

from app.channels.routing.friendly_errors import friendly_error_message, friendly_error_text
from app.channels.types import InboundMessage


class TestFriendlyErrorMessage:
    """Tests for the friendly_error_message() public function."""

    def test_timeout_zh(self) -> None:
        msg_in = InboundMessage(
            channel="test",
            sender_id="u1",
            content="hi",
            metadata={"locale": "zh-CN"},
        )
        msg, _ = friendly_error_message(Exception("connection timeout"), msg=msg_in)
        assert "超时" in msg

    def test_rate_limit(self) -> None:
        msg, ref_id = friendly_error_message(Exception("429 too many requests rate limit"))
        assert "rate limit" in msg.lower()
        assert ref_id in msg
        assert len(ref_id) == 8

    def test_overloaded(self) -> None:
        msg, ref_id = friendly_error_message(Exception("overloaded_error"))
        assert "overloaded" in msg.lower()
        assert ref_id in msg
        assert len(ref_id) == 8

    def test_billing(self) -> None:
        msg, _ = friendly_error_message(Exception("insufficient balance"))
        assert "configuration issue" in msg.lower()

    def test_auth(self) -> None:
        msg, _ = friendly_error_message(Exception("invalid api key"))
        assert "configuration issue" in msg.lower()

    def test_timeout(self) -> None:
        msg, _ = friendly_error_message(Exception("connection timeout"))
        assert "timed out" in msg.lower()

    def test_context_overflow(self) -> None:
        msg, _ = friendly_error_message(Exception("context_length_exceeded"))
        assert "too long" in msg.lower()

    def test_unknown(self) -> None:
        msg, ref_id = friendly_error_message(RuntimeError("some random error"))
        assert "Something went wrong" in msg
        assert f"[ref: {ref_id}]" in msg

    def test_ref_id_unique(self) -> None:
        _, r1 = friendly_error_message(Exception("err1"))
        _, r2 = friendly_error_message(Exception("err2"))
        assert r1 != r2

    def test_no_internal_leak(self) -> None:
        """Friendly messages never contain the raw exception text."""
        raw = "INTERNAL_SECRET_PATH=/opt/app/secrets.json"
        msg, _ = friendly_error_message(Exception(raw))
        assert raw not in msg
        assert "SECRET" not in msg


@pytest.mark.parametrize("kind", list(ErrorKind))
def test_every_error_kind_has_catalog_text(kind: ErrorKind) -> None:
    text, ref_id = friendly_error_text(kind)

    assert text.strip().endswith(f"[ref: {ref_id}]")
    assert text.strip() != f"[ref: {ref_id}]"
    assert "error_" not in text


def test_error_kind_text_follows_message_locale() -> None:
    msg_in = InboundMessage(channel="test", sender_id="u1", content="hi", metadata={"locale": "zh-CN"})

    zh, _ = friendly_error_text(ErrorKind.BILLING, msg_in)
    en, _ = friendly_error_text(ErrorKind.BILLING)

    assert zh != en
    assert "配置" in zh
