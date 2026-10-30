"""Cooldown hint units: below five minutes a wait stays in seconds, a longer one is spelled in its two largest units."""

import json
from pathlib import Path

import pytest

from myrm_agent_harness.agent.errors.diagnostics import i18n
from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager

_LOCALES = ("en", "zh-CN", "ja", "ko", "de")
_LOCALES_DIR = Path(i18n.__file__).parent / "locales"

# Each wait with the locale keys (and the number each is formatted with) it must be spelled with. Together they use
# every unit word in both plural forms, so a key no wait is spelled with is a key the renderer never reads.
_SPELLINGS = (
    (1, (("second_one", 1),)),
    (2, (("second_other", 2),)),
    (300, (("minute_other", 5),)),
    (3600, (("hour_one", 1),)),
    (7200, (("hour_other", 2),)),
    (3660, (("hour_one", 1), ("minute_one", 1))),
    (7320, (("hour_other", 2), ("minute_other", 2))),
    (86400, (("day_one", 1),)),
    (172800, (("day_other", 2),)),
    (90000, (("day_one", 1), ("hour_one", 1))),
)


def _bundle(locale: str) -> dict[str, str]:
    flat = json.loads((_LOCALES_DIR / f"{locale}.json").read_text(encoding="utf-8"))
    return {
        key.removeprefix("cooldown_hint_"): value for key, value in flat.items() if key.startswith("cooldown_hint_")
    }


@pytest.mark.parametrize(
    ("seconds", "spelled"),
    [
        (1, "1 second"),
        (299, "299 seconds"),
        (300, "5 minutes"),
        (301, "6 minutes"),
        (2820, "47 minutes"),
        (3540, "59 minutes"),
        (3541, "1 hour"),
        (3599, "1 hour"),
        (3600, "1 hour"),
        (3601, "1 hour 1 minute"),
        (23000, "6 hours 24 minutes"),
        (86340, "23 hours 59 minutes"),
        (86341, "1 day"),
        (86399, "1 day"),
        (86400, "1 day"),
        (90000, "1 day 1 hour"),
        (604800, "7 days"),
        (604801, "7 days 1 hour"),
    ],
)
def test_a_wait_below_five_minutes_stays_in_seconds_and_a_longer_one_rounds_up_into_its_largest_units(
    seconds: int, spelled: str
) -> None:
    assert format_cooldown_hint(seconds * 1000, "en") == f" Retry after {spelled}."


@pytest.mark.parametrize(
    ("locale", "seconds", "sentence"),
    [
        ("zh-CN", 23000, " 请等待6小时24分钟后重试。"),
        ("zh-CN", 2820, " 请等待47分钟后重试。"),
        ("zh-CN", 90000, " 请等待1天1小时后重试。"),
        ("ja", 23000, " 6時間24分後に再試行してください。"),
        ("ko", 23000, " 6시간 24분 후에 다시 시도하세요."),
        ("de", 23000, " Versuchen Sie es in 6 Stunden 24 Minuten erneut."),
        ("de", 172800, " Versuchen Sie es in 2 Tagen erneut."),
    ],
)
def test_a_long_wait_reads_in_the_callers_language(locale: str, seconds: int, sentence: str) -> None:
    assert format_cooldown_hint(seconds * 1000, locale) == sentence


@pytest.mark.parametrize(
    ("locale", "seconds", "words"),
    [
        pytest.param(locale, seconds, words, id=f"{locale}-{seconds}s")
        for locale in _LOCALES
        for seconds, words in _SPELLINGS
    ],
)
def test_a_bundled_locale_spells_a_wait_with_its_own_template_joiner_and_unit_words(
    locale: str, seconds: int, words: tuple[tuple[str, int], ...]
) -> None:
    bundle = _bundle(locale)
    duration = bundle["joiner"].join(bundle[key].format(n=n) for key, n in words)

    assert format_cooldown_hint(seconds * 1000, locale) == bundle["template"].format(duration=duration)


@pytest.mark.parametrize("locale", _LOCALES)
def test_every_cooldown_hint_key_of_a_bundled_locale_is_one_a_wait_is_spelled_with(locale: str) -> None:
    spelled_with = {"template", "joiner"} | {key for _, words in _SPELLINGS for key, _ in words}

    assert spelled_with == set(_bundle(locale))


def test_a_custom_bundle_without_the_hour_words_states_a_long_wait_in_its_own_seconds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = {"_cooldown_hint": {"template": " Warte {duration}.", "second_one": "{n}s", "second_other": "{n}s"}}
    monkeypatch.setitem(get_locale_manager()._translations, "xx", bundle)

    assert format_cooldown_hint(23_000_000, "xx") == " Warte 23000s."


def test_a_custom_bundle_with_only_the_other_form_of_a_unit_uses_it_for_one_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = {"_cooldown_hint": {"template": " Warte {duration}.", "hour_other": "{n}h"}}
    monkeypatch.setitem(get_locale_manager()._translations, "xx", bundle)

    assert format_cooldown_hint(3_600_000, "xx") == " Warte 1h."


def test_without_any_bundle_the_wait_is_an_english_sentence_in_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_locale_manager(), "_translations", {})

    assert format_cooldown_hint(23_000_000, "en") == " Retry after 23000 seconds."
