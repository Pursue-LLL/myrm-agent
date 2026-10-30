"""Tests for how the engine maps a requested locale onto the catalog language that serves it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.channels.i18n.engine import I18nEngine


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Catalogs for en, zh-CN, de and it (JSON), en and fr (Fluent), and a decoy JSON outside the root."""
    root = tmp_path / "root"
    root.mkdir()
    for language, text in {"en": "Hello", "zh-CN": "你好", "de": "Hallo", "it": "Ciao"}.items():
        (root / f"{language}.json").write_text(json.dumps({"hello": text}), encoding="utf-8")
    (root / "en.ftl").write_text("greeting = Hello\n", encoding="utf-8")
    (root / "fr.ftl").write_text("greeting = Bonjour\n", encoding="utf-8")
    (tmp_path / "secret.json").write_text(json.dumps({"hello": "OUTSIDE"}), encoding="utf-8")
    return root


@pytest.fixture
def engine(root: Path) -> I18nEngine:
    eng = I18nEngine()
    eng.add_root(str(root))
    return eng


@pytest.mark.parametrize(
    ("locale", "expected"),
    [
        ("en-GB", "Hello"),
        ("EN-us", "Hello"),
        ("zh-HK", "你好"),
        ("zh-Hans-CN", "你好"),
        ("zh_CN", "你好"),
        ("de-AT", "Hallo"),
        ("it-IT", "Ciao"),
        ("pt-BR", "Hello"),
        ("", "Hello"),
        (None, "Hello"),
    ],
)
def test_a_locale_is_served_from_the_first_fallback_that_has_a_catalog(
    engine: I18nEngine, locale: str | None, expected: str
) -> None:
    assert engine.format_value(locale, "hello") == expected


def test_a_language_that_only_has_a_fluent_catalog_is_served(engine: I18nEngine) -> None:
    assert engine.format_value("fr-CA", "greeting") == "Bonjour"


def test_distinct_locale_strings_without_a_catalog_share_one_localization(engine: I18nEngine) -> None:
    for index in range(50):
        engine.format_value(f"{chr(97 + index // 26)}{chr(97 + index % 26)}-{index}", "greeting")

    assert len(engine._localizations) == 1
    assert len(engine._json_catalogs) == 1


@pytest.mark.parametrize("locale", ["../secret", "../root/en", "a/b", "/etc/passwd", "en.json", "\x00"])
def test_a_locale_that_is_not_a_catalog_name_never_reaches_a_file(engine: I18nEngine, locale: str) -> None:
    assert engine.format_value(locale, "hello") == "Hello"
    assert locale not in engine._json_catalogs


def test_a_catalog_registered_after_the_first_request_is_served(engine: I18nEngine, tmp_path: Path) -> None:
    assert engine.format_value("es-MX", "greeting") == "Hello"

    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "es.ftl").write_text("greeting = Hola\n", encoding="utf-8")
    engine.add_root(str(extra))

    assert engine.format_value("es-MX", "greeting") == "Hola"
