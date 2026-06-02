"""Tests for JSON-string coercion in config_loader."""

from app.core.channel_bridge.config_loader import _coerce_config_dict
from app.core.channel_bridge.config_parsers import extract_active_search_config


def test_coerce_config_dict_parses_json_string() -> None:
    raw = '{"searchServiceConfigs": [{"enabled": true, "role": "primary", "search_service": "tavily", "api_key": "k"}]}'
    parsed = _coerce_config_dict(raw)
    assert parsed is not None
    assert extract_active_search_config(parsed) is not None


def test_coerce_config_dict_passes_through_dict() -> None:
    raw = {"embeddingApplied": True}
    assert _coerce_config_dict(raw) == raw
