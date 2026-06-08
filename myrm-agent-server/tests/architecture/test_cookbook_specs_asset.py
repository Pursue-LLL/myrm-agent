"""Validate bundled Ollama hardware cookbook asset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _myrm_agent_root() -> Path:
    return _server_root().parent


def _brand_public_cookbook_path() -> Path | None:
    candidate = (
        _myrm_agent_root().parent
        / "myrm-agent-brand"
        / "myrm-website"
        / "public"
        / "cookbook_specs.json"
    )
    return candidate if candidate.is_file() else None


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


def test_cookbook_specs_matches_brand_public_mirror() -> None:
    """Bundled asset must match myrm-agent-brand CDN source when monorepo sibling is checked out."""
    brand_path = _brand_public_cookbook_path()
    if brand_path is None:
        pytest.skip("myrm-agent-brand not present; OSS CI skips brand mirror parity")

    bundled_path = _server_root() / "assets" / "cookbook_specs.json"
    bundled_digest = hashlib.sha256(bundled_path.read_bytes()).hexdigest()
    brand_digest = hashlib.sha256(brand_path.read_bytes()).hexdigest()
    assert bundled_digest == brand_digest, (
        "cookbook_specs.json drift: server/assets vs myrm-agent-brand/myrm-website/public "
        f"(bundled={bundled_digest[:12]}…, brand={brand_digest[:12]}…)"
    )
