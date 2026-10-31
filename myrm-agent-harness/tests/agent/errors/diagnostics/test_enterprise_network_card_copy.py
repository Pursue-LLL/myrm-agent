"""The failure cards that send a user to the enterprise network setting tell them it needs a restart.

The setting reaches the HTTP clients a process has already built only after a restart (``infra/tls_compat.py``), and the
settings page says the same, so a user who flips it on the strength of a card and sees the error again is told why.
Both TLS cards carry the same last step in every language; the keyword is what each language's catalog uses for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from myrm_agent_harness.agent.errors.diagnostics.i18n import manager as manager_module

_LOCALES = Path(manager_module.__file__).parent / "locales"
_RESTART_WORDING = {
    "en": "restart",
    "zh-CN": "重启",
    "zh-TW": "重新啟動",
    "ja": "再起動",
    "ko": "다시 시작",
    "de": "neu starten",
}
_CARDS = ("tls_certificate_resolution_steps", "tls_transient_resolution_steps")


def _last_steps(locale: str) -> list[str]:
    bundle: dict[str, list[str]] = json.loads((_LOCALES / f"{locale}.json").read_text(encoding="utf-8"))
    return [bundle[card][-1] for card in _CARDS]


def test_every_shipped_locale_is_covered() -> None:
    assert {path.stem for path in _LOCALES.glob("*.json")} == set(_RESTART_WORDING)


@pytest.mark.parametrize("locale", sorted(_RESTART_WORDING))
def test_the_step_that_names_the_setting_says_to_restart(locale: str) -> None:
    for step in _last_steps(locale):
        assert _RESTART_WORDING[locale] in step


@pytest.mark.parametrize("locale", sorted(_RESTART_WORDING))
def test_both_tls_cards_give_the_same_last_step(locale: str) -> None:
    certificate_step, transient_step = _last_steps(locale)

    assert certificate_step == transient_step
