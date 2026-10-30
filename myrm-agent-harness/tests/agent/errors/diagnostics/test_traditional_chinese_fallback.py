"""A Traditional Chinese request is answered in Simplified Chinese, not English, until a Traditional bundle exists.

The diagnostics ship no ``zh-TW`` bundle. A locale with no bundle used to fall straight to English, so a Traditional
Chinese system (``LANG=zh_TW.UTF-8``) read English diagnostics while a Simplified one read Chinese.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic
from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import LocaleManager, get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.recovery_actions import build_recovery_actions

_TRADITIONAL = ["zh-TW", "zh_TW", "zh-HK", "zh-Hant", "zh-Hant-TW"]


@pytest.fixture
def manager() -> LocaleManager:
    return get_locale_manager()


@pytest.mark.parametrize("locale", _TRADITIONAL)
def test_a_traditional_request_reads_the_simplified_message(locale: str, manager: LocaleManager) -> None:
    assert manager.translate("rate_limit", "user_message", locale) == manager.translate(
        "rate_limit", "user_message", "zh-CN"
    )


@pytest.mark.parametrize("locale", _TRADITIONAL)
def test_a_traditional_request_reads_the_simplified_steps(locale: str, manager: LocaleManager) -> None:
    assert manager.translate("rate_limit", "resolution_steps", locale) == manager.translate(
        "rate_limit", "resolution_steps", "zh-CN"
    )


def test_an_optional_text_follows_the_same_fallback(manager: LocaleManager) -> None:
    assert manager.translate_optional("rate_limit", "wait_step", "zh-TW") == manager.translate_optional(
        "rate_limit", "wait_step", "zh-CN"
    )


def test_the_system_locale_of_a_traditional_chinese_machine_reads_chinese(
    manager: LocaleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MYRM_LOCALE", raising=False)
    monkeypatch.setenv("LC_ALL", "zh_TW.UTF-8")

    text = manager.translate("rate_limit", "user_message")

    assert text == manager.translate("rate_limit", "user_message", "zh-CN")


def test_a_host_bundle_for_traditional_chinese_is_used_and_the_rest_stays_simplified(
    manager: LocaleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(manager._translations, "zh-TW", {"rate_limit": {"user_message": "請求太頻繁"}})

    assert manager.translate("rate_limit", "user_message", "zh-TW") == "請求太頻繁"
    assert manager.translate("rate_limit", "resolution_steps", "zh-TW") == manager.translate(
        "rate_limit", "resolution_steps", "zh-CN"
    )


def test_other_languages_still_fall_back_to_english_only(manager: LocaleManager) -> None:
    assert manager.translate("rate_limit", "user_message", "fr") == manager.translate(
        "rate_limit", "user_message", "en"
    )
    assert manager.translate("rate_limit", "user_message", "ja") != manager.translate(
        "rate_limit", "user_message", "en"
    )


@pytest.mark.parametrize("locale", _TRADITIONAL)
def test_the_cooldown_sentence_is_spoken_in_simplified_chinese(locale: str) -> None:
    sentence = format_cooldown_hint(90_000, locale)

    assert sentence == format_cooldown_hint(90_000, "zh-CN")
    assert sentence != format_cooldown_hint(90_000, "en")


@pytest.mark.parametrize("locale", _TRADITIONAL)
def test_the_recovery_buttons_are_labelled_in_simplified_chinese(locale: str) -> None:
    assert build_recovery_actions("api_key", locale) == build_recovery_actions("api_key", "zh-CN")


def test_a_diagnosis_for_a_traditional_chinese_user_is_chinese() -> None:
    result = LLMErrorDiagnostic.diagnose(Exception("429 too many requests"), locale="zh-TW")

    assert result.error_type == "rate_limit"
    assert "速率限制" in result.user_message
