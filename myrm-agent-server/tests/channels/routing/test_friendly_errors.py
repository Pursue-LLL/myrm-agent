"""Member-safe wording for failed channel turns: one localized sentence per error kind plus a reference id."""

from __future__ import annotations

from contextlib import AbstractContextManager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind

from app.channels.routing.friendly_errors import (
    ERROR_TYPE_METADATA_KEY,
    friendly_error_message,
    friendly_error_text,
    is_error_reply,
)
from app.channels.types import InboundMessage, OutboundMessage


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


def test_text_has_no_surrounding_whitespace() -> None:
    text, _ = friendly_error_text(ErrorKind.TIMEOUT)

    assert text == text.strip()


_OWNER_KINDS = (ErrorKind.BILLING, ErrorKind.AUTH, ErrorKind.MODEL_NOT_FOUND)
_LOCALES = ("en", "zh-CN", "zh-TW", "ja")


def _deployment(*, platform_budget: bool) -> AbstractContextManager[MagicMock]:
    return patch(
        "app.channels.routing.friendly_errors.get_deployment_capabilities",
        return_value=SimpleNamespace(uses_platform_budget=platform_budget),
    )


@pytest.mark.parametrize("locale", _LOCALES)
@pytest.mark.parametrize("kind", _OWNER_KINDS)
def test_owner_wording_replaces_the_generic_one_in_every_locale(kind: ErrorKind, locale: str) -> None:
    generic, _ = friendly_error_text(kind, locale=locale)
    with _deployment(platform_budget=False):
        owner, ref_id = friendly_error_text(kind, locale=locale, account_guidance=True)

    assert owner != generic
    assert owner.endswith(f"[ref: {ref_id}]")
    assert "error_" not in owner


@pytest.mark.parametrize("locale", _LOCALES)
def test_platform_billing_wording_differs_from_the_byok_one(locale: str) -> None:
    with _deployment(platform_budget=False):
        byok, _ = friendly_error_text(ErrorKind.BILLING, locale=locale, account_guidance=True)
    with _deployment(platform_budget=True):
        platform, _ = friendly_error_text(ErrorKind.BILLING, locale=locale, account_guidance=True)

    assert byok.rsplit(" [ref", 1)[0] != platform.rsplit(" [ref", 1)[0]
    assert "error_" not in platform


def test_platform_deployment_keeps_the_generic_credential_wording() -> None:
    with _deployment(platform_budget=True):
        owner, _ = friendly_error_text(ErrorKind.AUTH, account_guidance=True)
    generic, _ = friendly_error_text(ErrorKind.AUTH)

    assert owner.rsplit(" [ref", 1)[0] == generic.rsplit(" [ref", 1)[0]


@pytest.mark.parametrize("kind", [k for k in ErrorKind if k not in _OWNER_KINDS])
def test_other_kinds_ignore_account_guidance(kind: ErrorKind) -> None:
    generic, _ = friendly_error_text(kind)
    guided, _ = friendly_error_text(kind, account_guidance=True)

    assert guided.rsplit(" [ref", 1)[0] == generic.rsplit(" [ref", 1)[0]


def test_is_error_reply_reads_the_failed_turn_flag() -> None:
    def reply(metadata: dict[str, object] | None) -> OutboundMessage:
        return OutboundMessage(channel="test", recipient_id="r", user_id="u", content="x", metadata=metadata)

    assert is_error_reply(reply({ERROR_TYPE_METADATA_KEY: "billing"}))
    assert not is_error_reply(reply(None))
    assert not is_error_reply(reply({"sources": []}))
    assert not is_error_reply(reply({ERROR_TYPE_METADATA_KEY: ""}))


def test_error_kind_text_follows_message_locale() -> None:
    msg_in = InboundMessage(channel="test", sender_id="u1", content="hi", metadata={"locale": "zh-CN"})

    zh, _ = friendly_error_text(ErrorKind.BILLING, msg_in)
    en, _ = friendly_error_text(ErrorKind.BILLING)

    assert zh != en
    assert "配置" in zh
