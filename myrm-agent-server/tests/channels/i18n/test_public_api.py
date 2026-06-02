"""Tests for channel i18n public API and BCP 47 fallback behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.channels.i18n import (
    channel_t,
    get_locale_from_metadata,
    get_text,
    resolve_message_locale,
)
from app.channels.i18n.engine import I18nEngine
from app.channels.types import InboundMessage


def _inbound_message(**metadata: str) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hello",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=False,
        mentioned=False,
        metadata=dict(metadata),
    )


def test_get_text_daily_budget_blocked_uses_message_locale() -> None:
    en_msg = _inbound_message(locale="en")
    zh_msg = _inbound_message(locale="zh-CN")

    assert "budget" in get_text(en_msg, "daily_budget_blocked").lower()
    assert "预算" in get_text(zh_msg, "daily_budget_blocked")


def test_resolve_message_locale_prefers_explicit_locale() -> None:
    msg = _inbound_message(locale="zh-CN", language_code="en")
    assert resolve_message_locale(msg) == "zh-CN"


def test_resolve_message_locale_uses_language_code_when_locale_missing() -> None:
    msg = _inbound_message(language_code="en")
    assert resolve_message_locale(msg) == "en"


def test_get_locale_from_metadata_defaults_to_en() -> None:
    assert get_locale_from_metadata(None) == "en"


def test_get_locale_from_metadata_reads_locale_field() -> None:
    assert get_locale_from_metadata({"locale": "zh-CN"}) == "zh-CN"


def test_get_locale_from_metadata_uses_language_code_fallback() -> None:
    assert get_locale_from_metadata({"language_code": "en"}) == "en"


def test_bcp47_fallback_chain_includes_zh_cn_for_zh_tw() -> None:
    engine = I18nEngine()
    chain = engine._get_fallback_chain("zh-TW")
    assert "zh-TW" in chain
    assert "zh-CN" in chain
    assert "en" in chain


def test_channel_t_falls_back_to_en_for_unknown_locale() -> None:
    text = channel_t("de", "daily_budget_blocked")
    assert "budget" in text.lower()


def test_add_locale_root_json_override(tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> None:
    fresh_engine = I18nEngine()
    monkeypatch.setattr("app.channels.i18n.engine._engine", fresh_engine)

    root = tmp_path / "custom"
    root.mkdir()
    with open(root / "en.json", "w", encoding="utf-8") as handle:
        json.dump({"daily_budget_blocked": "Custom budget message"}, handle)

    fresh_engine.add_root(str(root))
    assert fresh_engine.format_value("en", "daily_budget_blocked") == "Custom budget message"
