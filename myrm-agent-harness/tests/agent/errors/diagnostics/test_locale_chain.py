"""A locale reads the bundle of its own language before English, whatever region or script the tag carries.

``LANG=ja_JP.UTF-8`` is the shape a real system reports: it carries a region, and the bundles are named by language.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import LocaleManager, get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.recovery_actions import build_recovery_actions

_REGIONAL = [
    ("ja-JP", "ja"),
    ("ja_JP", "ja"),
    ("de-DE", "de"),
    ("de-AT", "de"),
    ("ko-KR", "ko"),
    ("ko_KR", "ko"),
]


@pytest.fixture
def manager() -> LocaleManager:
    return get_locale_manager()


@pytest.mark.parametrize(("tag", "language"), _REGIONAL)
def test_a_regional_variant_reads_the_bundle_of_its_language(tag: str, language: str, manager: LocaleManager) -> None:
    message = manager.translate("rate_limit", "user_message", tag)

    assert message == manager.translate("rate_limit", "user_message", language)
    assert message != manager.translate("rate_limit", "user_message", "en")


@pytest.mark.parametrize(("tag", "language"), _REGIONAL)
def test_a_regional_variant_reads_the_steps_and_the_cooldown_of_its_language(tag: str, language: str) -> None:
    manager = get_locale_manager()

    assert manager.translate("rate_limit", "resolution_steps", tag) == manager.translate(
        "rate_limit", "resolution_steps", language
    )
    assert format_cooldown_hint(90_000, tag) == format_cooldown_hint(90_000, language)
    assert format_cooldown_hint(90_000, tag) != format_cooldown_hint(90_000, "en")


@pytest.mark.parametrize(("tag", "language"), _REGIONAL)
def test_the_buttons_and_the_text_of_a_regional_variant_share_a_language(tag: str, language: str) -> None:
    assert build_recovery_actions("api_key", tag) == build_recovery_actions("api_key", language)


@pytest.mark.parametrize(
    ("system_locale", "language"),
    [("ja_JP.UTF-8", "ja"), ("de_DE.UTF-8", "de"), ("ko_KR.UTF-8", "ko"), ("de_AT.UTF-8", "de")],
)
def test_the_system_locale_of_a_machine_reads_its_language(
    system_locale: str, language: str, manager: LocaleManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MYRM_LOCALE", raising=False)
    monkeypatch.setenv("LC_ALL", system_locale)

    text = manager.translate("rate_limit", "user_message")

    assert text == manager.translate("rate_limit", "user_message", language)
    assert text != manager.translate("rate_limit", "user_message", "en")


@pytest.mark.parametrize(
    ("locale", "chain"),
    [
        ("ja-JP", ("ja-JP", "ja", "en")),
        ("ja", ("ja", "en")),
        ("de_AT", ("de_AT", "de-AT", "de", "en")),
        ("JA-jp", ("JA-jp", "ja", "en")),
        ("en-US", ("en-US", "en")),
        ("fr", ("fr", "en")),
        ("C", ("C", "en")),
        ("zh-HK", ("zh-HK", "zh-TW", "zh-CN", "en")),
        ("zh_Hant", ("zh_Hant", "zh-TW", "zh-CN", "en")),
    ],
)
def test_the_chain_of_a_locale_is_itself_its_canonical_form_its_language_then_english(
    locale: str, chain: tuple[str, ...]
) -> None:
    assert LocaleManager().locale_chain(locale) == chain


def test_a_bundle_a_host_registers_for_a_region_joins_the_chain_of_its_language() -> None:
    manager = LocaleManager()
    manager.register_translations("pt-BR", {"rate_limit": {"user_message": "Limite de taxa"}})

    assert manager.locale_chain("pt-PT") == ("pt-PT", "pt-BR", "en")
    assert manager.translate("rate_limit", "user_message", "pt-PT") == "Limite de taxa"


def test_the_chain_names_each_locale_once() -> None:
    chain = LocaleManager().locale_chain("en")

    assert chain == ("en",)


def test_the_chinese_alias_key_is_not_a_supported_locale() -> None:
    assert "zh_cn" not in LocaleManager().get_supported_locales()


def test_an_underscore_chinese_tag_still_reads_the_simplified_bundle() -> None:
    manager = get_locale_manager()

    assert manager.translate("rate_limit", "user_message", "zh_cn") == manager.translate(
        "rate_limit", "user_message", "zh-CN"
    )
