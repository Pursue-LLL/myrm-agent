"""Integration: Traditional Chinese diagnostic copy ↔ the product UI's Traditional Chinese glossary.

The zh-TW diagnostics card is read next to screens whose wording the frontend owns: mainland terms that must not
appear (`scripts/i18n-glossary.json`) and glyphs that exist only in Simplified Chinese
(`scripts/zh-simplified-glyphs.txt`). The harness copy and its button labels are held to the same two lists, with the
same matching rules as the frontend's `verify:i18n` gate. The harness suite keeps a short sample of both lists, which
is all a build without the frontend can run.

This test is cross-layer by design: harness zh-TW catalogue + frontend glossary.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from myrm_agent_harness.agent.errors.diagnostics.i18n import manager as harness_i18n
from myrm_agent_harness.agent.errors.diagnostics.recovery_actions import build_recovery_actions

_HARNESS_LOCALES_DIR = Path(harness_i18n.__file__).parent / "locales"
_FRONTEND_SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "scripts"

# Every error type the diagnostics engine maps to recovery buttons.
_BUTTON_ERROR_TYPES = ("api_key", "billing", "model", "custom_model_not_found")


@dataclass(frozen=True)
class _Glossary:
    """The frontend's zh-TW word lists, matched the way `verify-i18n/parity-config.mjs` matches them."""

    forbidden: tuple[str, ...]
    simplified_glyphs: frozenset[str]

    def violations(self, text: str) -> list[str]:
        lowered = text.lower()
        hits = [
            pattern
            for pattern in self.forbidden
            if (re.search(pattern[1:-1], text, re.IGNORECASE) if _is_regex(pattern) else pattern.lower() in lowered)
        ]
        return hits + sorted({char for char in text if char in self.simplified_glyphs})


def _is_regex(pattern: str) -> bool:
    return len(pattern) > 2 and pattern.startswith("/") and pattern.endswith("/")


@pytest.fixture(scope="module")
def glossary() -> _Glossary:
    glossary_file = _FRONTEND_SCRIPTS_DIR / "i18n-glossary.json"
    glyphs_file = _FRONTEND_SCRIPTS_DIR / "zh-simplified-glyphs.txt"
    for required in (glossary_file, glyphs_file):
        if not required.is_file():
            pytest.skip(f"Frontend glossary file not found: {required}")
    forbidden = json.loads(glossary_file.read_text("utf-8"))["locales"]["zh-TW"]["forbidden"]
    return _Glossary(tuple(map(str, forbidden)), frozenset(glyphs_file.read_text("utf-8").strip()))


def _catalogue_texts(locale: str) -> list[str]:
    bundle: dict[str, str | list[str]] = json.loads((_HARNESS_LOCALES_DIR / f"{locale}.json").read_text("utf-8"))
    return [text for value in bundle.values() for text in (value if isinstance(value, list) else [value])]


def _button_labels(locale: str) -> list[str]:
    return [action["label"] for kind in _BUTTON_ERROR_TYPES for action in build_recovery_actions(kind, locale)]


_SURFACES: dict[str, Callable[[str], list[str]]] = {"catalogue": _catalogue_texts, "buttons": _button_labels}


@pytest.mark.parametrize("surface", _SURFACES)
def test_traditional_copy_follows_the_frontend_glossary(surface: str, glossary: _Glossary) -> None:
    texts = _SURFACES[surface]("zh-TW")
    offenders = {text: hits for text in texts if (hits := glossary.violations(text))}

    assert texts, f"no zh-TW {surface} texts were scanned"
    assert not offenders, f"zh-TW {surface} breaks the frontend glossary: {offenders}"


def test_the_scan_applies_each_rule_on_its_own(glossary: _Glossary) -> None:
    # Each sample uses only Traditional glyphs except for the one rule under test, so no rule can mask another.
    assert glossary.violations("請更新信息") == ["信息"], "mainland terms went undetected"
    assert glossary.violations("連線逾時，请檢查") == ["请"], "Simplified-only glyphs went undetected"
    assert glossary.violations("連線逾時，請檢查網路") == []


def test_a_glossary_entry_written_as_a_regex_matches_case_insensitively() -> None:
    glossary = _Glossary(("/abc/",), frozenset())

    assert glossary.violations("xABCx") == ["/abc/"]
    assert glossary.violations("xabx") == []
