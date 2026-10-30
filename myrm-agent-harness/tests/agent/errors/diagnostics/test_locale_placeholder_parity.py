"""Every bundled diagnostic locale defines every key of the English catalog and uses its placeholders.

A key a locale lacks renders in English without any sign of the gap. A placeholder the caller never supplies renders
as an empty string (``LocaleManager._safe_format``), which leaves dangling text such as "(~ tokens)" or "Available
models: " in front of the user.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import myrm_agent_harness.agent.errors.diagnostics.i18n as i18n_package

_LOCALES_DIR = Path(i18n_package.__file__).parent / "locales"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _load(locale_file: Path) -> dict[str, str | list[str]]:
    bundle: dict[str, str | list[str]] = json.loads(locale_file.read_text(encoding="utf-8"))
    return bundle


def _placeholders(value: str | list[str]) -> set[str]:
    texts = value if isinstance(value, list) else [value]
    return {name for text in texts for name in _PLACEHOLDER.findall(text)}


_ENGLISH = _load(_LOCALES_DIR / "en.json")
_OTHER_LOCALES = sorted(path for path in _LOCALES_DIR.glob("*.json") if path.stem != "en")


@pytest.mark.parametrize("locale_file", _OTHER_LOCALES, ids=lambda path: path.stem)
def test_locale_uses_only_the_placeholders_of_the_english_catalog(locale_file: Path) -> None:
    mismatches = {
        key: (sorted(_placeholders(value)), sorted(_placeholders(_ENGLISH[key])))
        for key, value in _load(locale_file).items()
        if key in _ENGLISH and _placeholders(value) != _placeholders(_ENGLISH[key])
    }

    assert not mismatches, f"{locale_file.name} placeholders differ from en.json (locale, english): {mismatches}"


@pytest.mark.parametrize("locale_file", _OTHER_LOCALES, ids=lambda path: path.stem)
def test_locale_defines_every_key_of_the_english_catalog(locale_file: Path) -> None:
    assert sorted(set(_ENGLISH) - set(_load(locale_file))) == []
    assert sorted(set(_load(locale_file)) - set(_ENGLISH)) == []
