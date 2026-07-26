"""Unit tests for custom skill source configuration persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.skills.custom_source_config import (
    CustomSourceConfig,
    CustomSourceEntry,
    add_custom_source,
    load_custom_sources,
    remove_custom_source,
    save_custom_sources,
)


@pytest.fixture(autouse=True)
def mock_config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect config path to a temp directory."""
    config_file = tmp_path / "skill_sources.json"
    monkeypatch.setattr(
        "app.core.skills.custom_source_config._get_config_path",
        lambda: config_file,
    )
    return config_file


class TestCustomSourceConfig:
    def test_from_dict_valid(self) -> None:
        data = {
            "sources": [
                {"url": "https://a.com", "source_type": "well-known", "label": "A", "healthy": True},
                {"url": "https://b.com", "source_type": "well-known", "label": "", "healthy": False},
            ]
        }
        config = CustomSourceConfig.from_dict(data)
        assert len(config.sources) == 2
        assert config.sources[0].url == "https://a.com"
        assert config.sources[1].healthy is False

    def test_from_dict_empty(self) -> None:
        config = CustomSourceConfig.from_dict({})
        assert config.sources == []

    def test_from_dict_invalid_entries_skipped(self) -> None:
        data = {"sources": ["invalid", 123, {"url": "https://valid.com"}]}
        config = CustomSourceConfig.from_dict(data)
        assert len(config.sources) == 1
        assert config.sources[0].url == "https://valid.com"

    def test_to_dict(self) -> None:
        config = CustomSourceConfig(sources=[
            CustomSourceEntry(url="https://x.com", source_type="well-known", label="X"),
        ])
        d = config.to_dict()
        assert d["sources"][0]["url"] == "https://x.com"


class TestLoadSaveCustomSources:
    def test_load_nonexistent_returns_empty(self) -> None:
        config = load_custom_sources()
        assert config.sources == []

    def test_save_and_load(self, mock_config_path: Path) -> None:
        config = CustomSourceConfig(sources=[
            CustomSourceEntry(url="https://test.com", label="Test"),
        ])
        save_custom_sources(config)
        assert mock_config_path.exists()

        loaded = load_custom_sources()
        assert len(loaded.sources) == 1
        assert loaded.sources[0].url == "https://test.com"

    def test_load_corrupted_json(self, mock_config_path: Path) -> None:
        mock_config_path.write_text("not valid json", encoding="utf-8")
        config = load_custom_sources()
        assert config.sources == []


class TestAddRemoveCustomSource:
    def test_add_source(self) -> None:
        entry = add_custom_source("https://new.com", "well-known", "New")
        assert entry.url == "https://new.com"

        config = load_custom_sources()
        assert len(config.sources) == 1

    def test_add_duplicate_raises(self) -> None:
        add_custom_source("https://dup.com")
        with pytest.raises(ValueError, match="already exists"):
            add_custom_source("https://dup.com")

    def test_remove_existing(self) -> None:
        add_custom_source("https://remove.com")
        removed = remove_custom_source("https://remove.com")
        assert removed is True
        config = load_custom_sources()
        assert len(config.sources) == 0

    def test_remove_nonexistent(self) -> None:
        removed = remove_custom_source("https://nope.com")
        assert removed is False
