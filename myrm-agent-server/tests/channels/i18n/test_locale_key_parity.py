"""Channel `.ftl` locale key parity tests.

The channel locale catalog is the single source of truth for every user-visible
system message (busy acks, topic/workspace bindings, progress labels, deliverable
notes). Missing keys silently degrade a locale to another language through the
BCP 47 fallback chain, so a gap in e.g. `ja.ftl` shows English (or Simplified
Chinese) to Japanese users.

These guards enforce that every locale file exposes the exact same key set as the
`en.ftl` reference:
1. No key is missing from any locale.
2. No locale carries an orphan key the reference does not have.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_LOCALES_DIR = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "channels"
    / "i18n"
    / "locales"
)

_REFERENCE_LOCALE = "en"

# A message key is a bare identifier (letters/digits/underscore/hyphen)
# terminated by ' =' at column 0. Continuation lines are indented and belong
# to the same message, so only lines starting at column 0 count as keys.
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+) =")


def _locale_names() -> tuple[str, ...]:
    """Every `.ftl` file present; new languages join the parity check automatically."""
    return tuple(sorted(path.stem for path in _LOCALES_DIR.glob("*.ftl")))


def _ftl_keys(locale: str) -> frozenset[str]:
    path = _LOCALES_DIR / f"{locale}.ftl"
    assert path.exists(), f"Missing locale file: {path}"
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _KEY_RE.match(line)
        if match:
            keys.add(match.group(1))
    return frozenset(keys)


@pytest.mark.architecture
def test_ftl_locales_share_identical_key_sets() -> None:
    """Every channel locale must expose the exact same message keys."""
    locales = _locale_names()
    assert _REFERENCE_LOCALE in locales, (
        f"Reference locale {_REFERENCE_LOCALE}.ftl missing under {_LOCALES_DIR}"
    )
    key_sets = {locale: _ftl_keys(locale) for locale in locales}
    reference_keys = key_sets[_REFERENCE_LOCALE]

    for locale, keys in key_sets.items():
        missing = reference_keys - keys
        extra = keys - reference_keys
        assert not missing and not extra, (
            f"FTL key mismatch between {_REFERENCE_LOCALE} and {locale}: "
            f"missing={sorted(missing)}, extra={sorted(extra)}. Missing keys "
            f"silently fall back to another language via BCP 47; add the "
            f"translation in {locale}.ftl."
        )
