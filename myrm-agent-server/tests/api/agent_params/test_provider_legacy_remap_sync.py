"""Ensure frontend and server legacy provider remap artifacts stay identical."""

from __future__ import annotations

from pathlib import Path


def test_provider_legacy_remap_json_matches_frontend_copy() -> None:
    server_root = Path(__file__).resolve().parents[3]
    repo_root = server_root.parent

    server_json = server_root / "app" / "services" / "agent" / "params" / "provider_legacy_remap.json"
    frontend_json = repo_root / "myrm-agent-frontend" / "src" / "store" / "config" / "provider_legacy_remap.json"

    assert server_json.is_file(), f"Missing server remap file: {server_json}"
    assert frontend_json.is_file(), f"Missing frontend remap file: {frontend_json}"
    assert server_json.read_bytes() == frontend_json.read_bytes()
