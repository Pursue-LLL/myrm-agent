"""Integration: ToolErrorCategory enum ↔ frontend i18n errorCategories key sync.

Ensures every harness ToolErrorCategory value has a matching i18n key
in ALL locale files, and vice-versa. Catches drift early (e.g. someone
adds a new enum member but forgets the i18n entry, or changes a value
without updating frontend translations).

This test is cross-layer by design: harness enum + frontend locales.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from myrm_agent_harness.agent.errors import ToolErrorCategory

FRONTEND_LOCALES_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "locales"

LOCALE_FILES = ("en.json", "zh.json", "ja.json", "zh-TW.json")

I18N_NAMESPACE = "progressSteps"
I18N_KEY_GROUP = "errorCategories"


def _load_error_categories(locale_file: Path) -> dict[str, str]:
    """Extract errorCategories from a locale JSON file."""
    data = json.loads(locale_file.read_text("utf-8"))
    namespace = data.get(I18N_NAMESPACE, {})
    return namespace.get(I18N_KEY_GROUP, {})


@pytest.fixture(scope="module")
def enum_values() -> frozenset[str]:
    return frozenset(member.value for member in ToolErrorCategory)


@pytest.fixture(scope="module", params=LOCALE_FILES)
def locale_categories(request: pytest.FixtureRequest) -> tuple[str, dict[str, str]]:
    locale_path = FRONTEND_LOCALES_DIR / request.param
    if not locale_path.exists():
        pytest.skip(f"Locale file not found: {locale_path}")
    return request.param, _load_error_categories(locale_path)


class TestEnumI18nSync:
    """Verify ToolErrorCategory and i18n errorCategories stay in sync."""

    def test_all_enum_values_have_i18n_keys(
        self,
        enum_values: frozenset[str],
        locale_categories: tuple[str, dict[str, str]],
    ) -> None:
        locale_name, categories = locale_categories
        missing = enum_values - set(categories.keys())
        assert not missing, f"[{locale_name}] ToolErrorCategory values missing i18n: {sorted(missing)}"

    def test_no_orphan_i18n_keys(
        self,
        enum_values: frozenset[str],
        locale_categories: tuple[str, dict[str, str]],
    ) -> None:
        locale_name, categories = locale_categories
        orphans = set(categories.keys()) - enum_values
        assert not orphans, f"[{locale_name}] i18n keys without ToolErrorCategory: {sorted(orphans)}"

    def test_no_empty_translations(
        self,
        locale_categories: tuple[str, dict[str, str]],
    ) -> None:
        locale_name, categories = locale_categories
        empty = [k for k, v in categories.items() if not v or not v.strip()]
        assert not empty, f"[{locale_name}] Empty translations for: {sorted(empty)}"


class TestEnumValueConsistency:
    """Verify enum values match expected patterns (lowercase_snake_case)."""

    @pytest.mark.parametrize("member", list(ToolErrorCategory))
    def test_value_is_lowercase_snake(self, member: ToolErrorCategory) -> None:
        assert member.value == member.value.lower(), f"{member.name} value should be lowercase: {member.value}"
        assert " " not in member.value, f"{member.name} value contains spaces: {member.value}"

    def test_no_duplicate_values(self) -> None:
        values = [m.value for m in ToolErrorCategory]
        assert len(values) == len(set(values)), f"Duplicate enum values: {[v for v in values if values.count(v) > 1]}"

    def test_all_locales_have_same_keys(self) -> None:
        """All locale files must define the exact same set of errorCategories keys."""
        all_keys: dict[str, set[str]] = {}
        for locale_file in LOCALE_FILES:
            path = FRONTEND_LOCALES_DIR / locale_file
            if path.exists():
                cats = _load_error_categories(path)
                all_keys[locale_file] = set(cats.keys())

        if len(all_keys) < 2:
            pytest.skip("Need at least 2 locale files to compare")

        reference_locale, reference_keys = next(iter(all_keys.items()))
        for locale, keys in all_keys.items():
            if locale == reference_locale:
                continue
            missing = reference_keys - keys
            extra = keys - reference_keys
            assert not missing and not extra, (
                f"Key mismatch between {reference_locale} and {locale}: missing={sorted(missing)}, extra={sorted(extra)}"
            )
