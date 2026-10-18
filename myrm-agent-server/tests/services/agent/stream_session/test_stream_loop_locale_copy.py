"""User-visible stream copy follows the chat locale instead of a fixed language."""

from __future__ import annotations

import pytest

from app.services.agent.stream_session.stream_loop import (
    _BUDGET_EXHAUSTED_NOTICE,
    _GATE_BLOCKED_FIELDS,
    _GATE_POLICY_NOTE,
    _PRIVACY_BLOCKED_FIELDS,
    _stream_locale,
)


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("zh-CN", "zh"),
        ("zh-TW", "zh"),
        ("zh", "zh"),
        ("en", "en"),
        ("en-US", "en"),
        ("ja", "en"),
        (None, "en"),
    ],
)
def test_stream_locale_resolves_chinese_and_falls_back_to_english(
    locale: str | None, expected: str
) -> None:
    assert _stream_locale(locale) == expected


def test_budget_notice_has_both_languages_and_no_cjk_in_english() -> None:
    assert set(_BUDGET_EXHAUSTED_NOTICE) == {"en", "zh"}
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in _BUDGET_EXHAUSTED_NOTICE["en"])
    assert any("\u4e00" <= ch <= "\u9fff" for ch in _BUDGET_EXHAUSTED_NOTICE["zh"])


def test_gate_and_privacy_copy_share_the_same_field_set_across_locales() -> None:
    assert _PRIVACY_BLOCKED_FIELDS["en"].keys() == _PRIVACY_BLOCKED_FIELDS["zh"].keys()
    assert _GATE_BLOCKED_FIELDS["en"].keys() == _GATE_BLOCKED_FIELDS["zh"].keys()
    assert set(_GATE_POLICY_NOTE) == {"en", "zh"}
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in _GATE_POLICY_NOTE["en"])
