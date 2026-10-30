"""normalize_locale / resolve_locale / is_chinese: which Chinese a tag names, and that the family stays one.

A tag naming Traditional Chinese keeps its own locale (``zh-TW``) so a catalog written for it can be served; every
other Chinese tag stays ``zh-CN``. ``is_chinese`` answers for the whole family, which is what prompt and tool text
branch on.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.utils.locale import is_chinese, normalize_locale, resolve_locale

_TRADITIONAL = [
    "zh-TW",
    "zh_TW",
    "ZH-tw",
    "zh-HK",
    "zh_hk",
    "zh-MO",
    "zh-Hant",
    "zh-hant",
    "zh-Hant-TW",
    "zh-Hant-CN",
    "zh-yue-HK",
    "zh-TW-x-private",
    "zh_TW.UTF-8",
]
_SIMPLIFIED = [
    "zh",
    "ZH",
    "zh-CN",
    "zh_CN",
    "zh-SG",
    "zh-Hans",
    "zh-hans",
    "zh-Hans-TW",
    "zh-Hans-HK",
    "zh-cmn-Hans-CN",
    "zh-yue",
    "zh-x-hant",
    "zh_CN.UTF-8",
]


@pytest.mark.parametrize("tag", _TRADITIONAL)
def test_a_tag_naming_traditional_chinese_keeps_its_own_locale(tag: str) -> None:
    assert normalize_locale(tag) == "zh-TW"


@pytest.mark.parametrize("tag", _SIMPLIFIED)
def test_every_other_chinese_tag_is_simplified(tag: str) -> None:
    assert normalize_locale(tag) == "zh-CN"


def test_the_script_decides_before_the_region() -> None:
    assert normalize_locale("zh-Hans-TW") == "zh-CN"
    assert normalize_locale("zh-Hant-CN") == "zh-TW"


@pytest.mark.parametrize("tag", [*_TRADITIONAL, *_SIMPLIFIED])
def test_normalizing_twice_changes_nothing(tag: str) -> None:
    # The router resolves a message's locale at ingress and again from the stored result.
    once = normalize_locale(tag)
    assert normalize_locale(once) == once


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("en-US", "en-US"), ("ja_JP", "ja-JP"), ("de", "de"), ("C", "en"), ("POSIX", "en"), ("", "en"), (None, "en")],
)
def test_a_tag_that_is_not_chinese_is_left_as_it_was(tag: str | None, expected: str) -> None:
    assert normalize_locale(tag) == expected


@pytest.mark.parametrize("tag", [*_TRADITIONAL, *_SIMPLIFIED])
def test_the_chinese_family_is_chinese(tag: str) -> None:
    assert is_chinese(tag)


@pytest.mark.parametrize("tag", ["en", "en-US", "ja", "ko-KR", "de", "", None])
def test_other_languages_are_not_chinese(tag: str | None) -> None:
    assert not is_chinese(tag)


def test_the_sender_s_traditional_tag_beats_the_owner_s_simplified_preference() -> None:
    assert resolve_locale(platform_locale="zh-hant", user_locale="zh-CN") == "zh-TW"


def test_the_owner_s_traditional_preference_is_kept() -> None:
    assert resolve_locale(user_locale="zh-TW") == "zh-TW"


def test_a_chinese_first_platform_without_a_preference_is_simplified() -> None:
    assert resolve_locale(channel="feishu") == "zh-CN"


def test_the_environment_locale_can_name_traditional_chinese(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_LOCALE", "zh_TW.UTF-8")

    assert resolve_locale() == "zh-TW"
