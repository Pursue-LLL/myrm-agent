"""Unit tests for server ClawHub registry mirror helpers."""

from __future__ import annotations

from app.core.skills.marketplace.clawhub_registry import (
    get_registry_presets,
    normalize_clawhub_registry_url,
)


def test_normalize_migrates_legacy_skillhub_cn() -> None:
    assert normalize_clawhub_registry_url("https://skillhub.cn") == (
        "https://skill.xfyun.cn"
    )


def test_normalize_empty_means_international_default() -> None:
    assert normalize_clawhub_registry_url("") == ""
    assert normalize_clawhub_registry_url("https://clawhub.ai") == ""


def test_registry_presets_include_cn_xfyun() -> None:
    presets = {item.id: item.url for item in get_registry_presets()}
    assert presets["intl"] == ""
    assert presets["cn"] == "https://skill.xfyun.cn"
