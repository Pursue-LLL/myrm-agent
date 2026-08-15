"""Tests for doctor_check on-disk config verification.

Covers every branch of verify_connector_config against temporary files:
missing file, unreadable/invalid content, missing entry, token mismatch,
and a fully verified config in both JSON and TOML layouts.
"""

import json
from pathlib import Path
from typing import Literal

from app.services.connect.doctor_check import (
    DOCTOR_CONFIG_FILE_MISSING,
    DOCTOR_ENTRY_MISSING,
    DOCTOR_FILE_UNREADABLE,
    DOCTOR_TOKEN_MISMATCH,
    DOCTOR_VERIFIED,
    hash_token,
    verify_connector_config,
)

TOKEN = "myrm_mcp_test_token_123"
TOKEN_HASH = hash_token(TOKEN)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _verify(
    path: Path,
    *,
    token_hash: str = TOKEN_HASH,
    instructions_key: str = "mcpServers",
    config_format: Literal["json_mcp", "toml_mcp"] = "json_mcp",
):
    return verify_connector_config(
        config_file_path=str(path),
        instructions_key=instructions_key,
        config_format=config_format,
        token_hash=token_hash,
    )


def _entry(token: str = TOKEN) -> dict[str, object]:
    return {
        "url": "http://127.0.0.1:8080/mcp",
        "transport": "streamable-http",
        "headers": {"Authorization": f"Bearer {token}"},
    }


class TestVerifyConnectorConfig:
    def test_returns_none_without_config_path(self, tmp_path: Path):
        verdict = verify_connector_config(
            config_file_path=None,
            instructions_key="mcpServers",
            config_format="json_mcp",
            token_hash=TOKEN_HASH,
        )
        assert verdict is None

    def test_verified_json_config(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        _write_json(config_file, {"mcpServers": {"other": {}, "myrm-memory": _entry()}})
        verdict = _verify(config_file)
        assert verdict is not None
        assert verdict.healthy is True
        assert verdict.detail == DOCTOR_VERIFIED

    def test_verified_toml_config(self, tmp_path: Path):
        config_file = tmp_path / "settings.toml"
        config_file.write_text(
            "[mcp_servers.myrm-memory]\n"
            'url = "http://127.0.0.1:8080/mcp"\n'
            '[mcp_servers.myrm-memory.headers]\n'
            f'Authorization = "Bearer {TOKEN}"\n',
            encoding="utf-8",
        )
        verdict = _verify(config_file, instructions_key="mcp_servers", config_format="toml_mcp")
        assert verdict is not None
        assert verdict.healthy is True
        assert verdict.detail == DOCTOR_VERIFIED

    def test_missing_config_file(self, tmp_path: Path):
        verdict = _verify(tmp_path / "does_not_exist.json")
        assert verdict is not None
        assert verdict.healthy is False
        assert verdict.detail == DOCTOR_CONFIG_FILE_MISSING

    def test_invalid_json_is_unreadable(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        config_file.write_text("{ not valid json", encoding="utf-8")
        verdict = _verify(config_file)
        assert verdict is not None
        assert verdict.healthy is False
        assert verdict.detail == DOCTOR_FILE_UNREADABLE

    def test_non_dict_json_is_unreadable(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        _write_json(config_file, [1, 2, 3])
        verdict = _verify(config_file)
        assert verdict is not None
        assert verdict.detail == DOCTOR_FILE_UNREADABLE

    def test_missing_entry(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        _write_json(config_file, {"mcpServers": {"other-agent": _entry()}})
        verdict = _verify(config_file)
        assert verdict is not None
        assert verdict.healthy is False
        assert verdict.detail == DOCTOR_ENTRY_MISSING

    def test_missing_servers_key(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        _write_json(config_file, {"something": "else"})
        verdict = _verify(config_file)
        assert verdict is not None
        assert verdict.healthy is False
        assert verdict.detail == DOCTOR_ENTRY_MISSING

    def test_token_mismatch(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        _write_json(config_file, {"mcpServers": {"myrm-memory": _entry("myrm_mcp_stale_token")}})
        verdict = _verify(config_file)
        assert verdict is not None
        assert verdict.healthy is False
        assert verdict.detail == DOCTOR_TOKEN_MISMATCH

    def test_entry_without_bearer_token_is_mismatch(self, tmp_path: Path):
        config_file = tmp_path / "mcp.json"
        _write_json(config_file, {"mcpServers": {"myrm-memory": {"headers": {}}}})
        verdict = _verify(config_file)
        assert verdict is not None
        assert verdict.healthy is False
        assert verdict.detail == DOCTOR_TOKEN_MISMATCH

    def test_relative_path_is_resolved_from_cwd(self, tmp_path: Path, monkeypatch):
        config_file = tmp_path / "mcp.json"
        _write_json(config_file, {"mcpServers": {"myrm-memory": _entry()}})
        monkeypatch.chdir(tmp_path)
        verdict = _verify(Path("mcp.json"))
        assert verdict is not None
        assert verdict.healthy is True
