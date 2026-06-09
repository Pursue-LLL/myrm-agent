"""Ensure shared legacy provider remap artifact is present, valid, and loaded by server."""

from __future__ import annotations

import json
from pathlib import Path


def _repo_root() -> Path:
    server_root = Path(__file__).resolve().parents[3]
    return server_root.parent


def _load_json_remap(path: Path) -> dict[str, str]:
    raw_obj = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw_obj, dict), "provider_legacy_remap.json must contain a JSON object"
    result: dict[str, str] = {}
    for key_obj, val_obj in raw_obj.items():
        assert isinstance(key_obj, str) and isinstance(val_obj, str), (
            "provider_legacy_remap.json keys and values must be strings"
        )
        result[key_obj] = val_obj
    return result


def test_provider_legacy_remap_json_is_valid_shared_artifact() -> None:
    shared_json = _repo_root() / "shared" / "config" / "provider_legacy_remap.json"

    assert shared_json.is_file(), f"Missing shared remap file: {shared_json}"

    _load_json_remap(shared_json)


def test_server_provider_remap_matches_shared_json() -> None:
    shared_json = _repo_root() / "shared" / "config" / "provider_legacy_remap.json"
    expected = _load_json_remap(shared_json)

    from app.services.agent.params.providers import LEGACY_STORAGE_PROVIDER_ID_REMAP

    assert LEGACY_STORAGE_PROVIDER_ID_REMAP == expected


def test_normalize_storage_provider_id_matches_shared_remap_variants() -> None:
    from app.services.agent.params.providers import normalize_storage_provider_id

    assert normalize_storage_provider_id("Google") == "gemini"
    assert normalize_storage_provider_id("GOOGLE") == "gemini"
    assert normalize_storage_provider_id("google-genai") == "gemini"
    assert normalize_storage_provider_id("QWEN") == "dashscope"
    assert normalize_storage_provider_id("openai") == "openai"
