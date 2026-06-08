"""Ensure shared legacy provider remap artifact is present and valid."""

from __future__ import annotations

import json
from pathlib import Path


def _repo_root() -> Path:
    server_root = Path(__file__).resolve().parents[3]
    return server_root.parent


def test_provider_legacy_remap_json_is_valid_shared_artifact() -> None:
    shared_json = _repo_root() / "shared" / "config" / "provider_legacy_remap.json"

    assert shared_json.is_file(), f"Missing shared remap file: {shared_json}"

    raw_obj = json.loads(shared_json.read_text(encoding="utf-8"))
    assert isinstance(raw_obj, dict), "provider_legacy_remap.json must contain a JSON object"
    for key_obj, val_obj in raw_obj.items():
        assert isinstance(key_obj, str) and isinstance(val_obj, str), (
            "provider_legacy_remap.json keys and values must be strings"
        )
