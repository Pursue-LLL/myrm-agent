"""A Traditional Chinese request is answered in Traditional Chinese: the message, the steps, the wait, and the buttons.

``zh-TW`` ships its own diagnostics bundle and its own recovery button labels, so a Traditional Chinese system
(``LANG=zh_TW.UTF-8``) reads neither English nor Simplified Chinese.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import myrm_agent_harness.agent.errors.diagnostics.i18n as i18n_package
from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic
from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import LocaleManager, get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.recovery_actions import _LABELS, _LABELS_I18N, build_recovery_actions

_TRADITIONAL = ["zh-TW", "zh_TW", "zh-HK", "zh-Hant", "zh-Hant-TW"]
_BUNDLE = Path(i18n_package.__file__).parent / "locales" / "zh-TW.json"

# Simplified-only glyphs and mainland terms the Traditional wording must not carry (the product UI's zh-TW glossary).
_SIMPLIFIED_GLYPHS = "设连时务钥错请账网这个进检测证误败权开关启动态资页数据过载处发览应顾项档规则让储称"
_MAINLAND_TERMS = ("支持", "保存", "信息", "窗口", "兼容", "搜索", "界面", "文件夹", "插件", "刷新")


@pytest.fixture
def manager() -> LocaleManager:
    return get_locale_manager()


def _traditional_texts() -> list[str]:
    bundle: dict[str, str | list[str]] = json.loads(_BUNDLE.read_text(encoding="utf-8"))
    texts = [text for value in bundle.values() for text in (value if isinstance(value, list) else [value])]
    return [*texts, *_LABELS_I18N["zh-TW"].values()]


def test_the_traditional_bundle_is_shipped(manager: LocaleManager) -> None:
    assert "zh-TW" in manager.get_supported_locales()


@pytest.mark.parametrize("locale", _TRADITIONAL)
def test_a_traditional_request_reads_the_traditional_message(locale: str, manager: LocaleManager) -> None:
    assert manager.translate("rate_limit", "user_message", locale) == "已超出 API 速率限制"
    assert manager.translate("timeout", "user_message", locale) == "LLM 請求逾時"


@pytest.mark.parametrize("locale", _TRADITIONAL)
def test_a_traditional_request_reads_the_traditional_steps(locale: str, manager: LocaleManager) -> None:
    assert manager.translate("api_key", "resolution_steps", locale)[0] == "在 設定 > 模型服務 中更新您的 API 金鑰"


def test_an_optional_text_is_traditional(manager: LocaleManager) -> None:
    assert manager.translate_optional("rate_limit", "wait_step", "zh-TW") == "等待 60 秒後重試"


def test_the_system_locale_of_a_traditional_chinese_machine_reads_traditional_chinese(
    manager: LocaleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MYRM_LOCALE", raising=False)
    monkeypatch.setenv("LC_ALL", "zh_TW.UTF-8")

    assert manager.translate("rate_limit", "user_message") == "已超出 API 速率限制"


def test_a_simplified_request_still_reads_simplified_chinese(manager: LocaleManager) -> None:
    assert manager.translate("rate_limit", "user_message", "zh-CN") == "API 速率限制超出"
    assert manager.translate("rate_limit", "user_message", "zh-Hans") == "API 速率限制超出"


@pytest.mark.parametrize("locale", _TRADITIONAL)
@pytest.mark.parametrize(
    ("wait_ms", "sentence"),
    [
        (90_000, " 請等待90秒後重試。"),
        (47 * 60_000, " 請等待47分鐘後重試。"),
        ((6 * 60 + 24) * 60_000, " 請等待6小時24分鐘後重試。"),
        (7 * 86_400_000, " 請等待7天後重試。"),
    ],
    ids=["seconds", "minutes", "two_units", "days"],
)
def test_the_cooldown_sentence_is_spoken_in_traditional_chinese(locale: str, wait_ms: int, sentence: str) -> None:
    assert format_cooldown_hint(wait_ms, locale) == sentence


@pytest.mark.parametrize("locale", _TRADITIONAL)
@pytest.mark.parametrize(
    ("error_type", "label"),
    [("api_key", "更新 API 金鑰"), ("billing", "儲值餘額"), ("model", "切換模型")],
    ids=["api_key", "billing", "model"],
)
def test_the_recovery_buttons_are_labelled_in_traditional_chinese(locale: str, error_type: str, label: str) -> None:
    assert [action["label"] for action in build_recovery_actions(error_type, locale)] == [label]


def test_a_diagnosis_for_a_traditional_chinese_user_is_traditional_chinese() -> None:
    result = LLMErrorDiagnostic.diagnose(Exception("429 too many requests"), locale="zh-TW")

    assert result.error_type == "rate_limit"
    assert result.user_message == "已超出 API 速率限制"
    assert result.locale == "zh-TW"


def test_every_bundled_locale_but_english_has_its_own_recovery_labels() -> None:
    assert set(_LABELS_I18N) == {path.stem for path in _BUNDLE.parent.glob("*.json")} - {"en"}


@pytest.mark.parametrize("locale", sorted(_LABELS_I18N))
def test_a_label_table_names_every_button(locale: str) -> None:
    assert set(_LABELS_I18N[locale]) == set(_LABELS)


def test_the_traditional_wording_carries_no_simplified_glyph_or_mainland_term() -> None:
    texts = _traditional_texts()

    assert [text for text in texts if any(glyph in text for glyph in _SIMPLIFIED_GLYPHS)] == []
    assert [text for text in texts if any(term in text for term in _MAINLAND_TERMS)] == []
