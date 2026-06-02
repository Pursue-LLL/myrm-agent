"""Tests for I18nEngine safe formatting and deep JSON flattening."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.channels.i18n.engine import I18nEngine, channel_t


@pytest.fixture
def temp_locale_root(tmp_path: Path) -> Path:
    """Create a temporary locale directory with nested JSON."""
    locales_dir = tmp_path / "locales"
    locales_dir.mkdir()
    data = {
        "flat_key": "Hello {name}",
        "errors": {
            "llm": {
                "timeout_user_message": "Request timed out after {seconds}s",
            }
        },
        "steps": ["Step 1: {action}", "Step 2"],
    }
    with open(locales_dir / "en.json", "w", encoding="utf-8") as f:
        json.dump(data, f)
    return locales_dir


@pytest.fixture
def engine(temp_locale_root: Path) -> I18nEngine:
    eng = I18nEngine()
    eng.add_root(str(temp_locale_root))
    return eng


def test_deep_flatten_nested_keys(engine: I18nEngine) -> None:
    result = engine.format_value("en", "errors_llm_timeout_user_message", seconds=30)
    assert result == "Request timed out after 30s"


def test_safe_format_missing_kwargs_preserves_placeholder(engine: I18nEngine) -> None:
    result = engine.format_value("en", "flat_key")
    assert result == "Hello {name}"


def test_safe_format_partial_kwargs(engine: I18nEngine) -> None:
    result = engine.format_value("en", "flat_key", name="Alice")
    assert result == "Hello Alice"


def test_safe_format_list_with_missing_kwargs(engine: I18nEngine) -> None:
    result = engine.format_value("en", "steps")
    assert result == ["Step 1: {action}", "Step 2"]


def test_channel_t_delegates_to_engine(engine: I18nEngine, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.channels import i18n as i18n_module

    monkeypatch.setattr(i18n_module.engine, "_engine", engine)
    assert channel_t("en", "flat_key", name="Bob") == "Hello Bob"


def test_format_value_returns_key_on_miss(engine: I18nEngine) -> None:
    assert engine.format_value("en", "missing_catalog_key_xyz") == "missing_catalog_key_xyz"


def test_json_catalog_invalid_file_is_skipped(
    engine: I18nEngine, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not-json", encoding="utf-8")
    engine.add_root(str(tmp_path))
    # Trigger load for a locale matching the bad file name
    engine._load_json_catalog("bad")
    assert engine._json_catalogs["bad"] == {}


def test_channel_t_daily_budget_blocked_catalog() -> None:
    en_text = channel_t("en", "daily_budget_blocked")
    zh_text = channel_t("zh-CN", "daily_budget_blocked")
    assert "budget" in en_text.lower()
    assert "预算" in zh_text
