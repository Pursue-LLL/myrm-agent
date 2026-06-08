"""Validate bundled Ollama hardware cookbook asset."""

from __future__ import annotations

import json
from pathlib import Path


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_cookbook_specs_json_is_valid_bundled_asset() -> None:
    path = _server_root() / "assets" / "cookbook_specs.json"
    assert path.is_file(), f"Missing bundled cookbook asset: {path}"

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, list), "cookbook_specs.json must be a JSON array"
    assert len(raw) >= 1, "cookbook_specs.json must contain at least one model spec"

    required_keys = {"id", "name", "description", "req_vram_gb"}
    for index, item in enumerate(raw):
        assert isinstance(item, dict), f"Entry {index} must be an object"
        missing = required_keys - set(item.keys())
        assert not missing, f"Entry {index} missing keys: {sorted(missing)}"
        assert isinstance(item["id"], str) and item["id"], f"Entry {index} id must be non-empty string"
        assert isinstance(item["req_vram_gb"], (int, float)), f"Entry {index} req_vram_gb must be numeric"
