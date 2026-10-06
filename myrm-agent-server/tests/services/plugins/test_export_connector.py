"""Connector declarations that leave the machine: secret names only, nothing that only works here."""

from __future__ import annotations

import pytest

from app.services.plugins._export_connector import connector_from_config, secret_names_of
from app.services.plugins._export_models import Omit


def _stdio(**overrides: object) -> dict[str, object]:
    return {"name": "sqlite", "type": "stdio", "command": "uvx", "args": ["mcp-server-sqlite"], **overrides}


def _remote(**overrides: object) -> dict[str, object]:
    return {"name": "docs", "type": "streamable_http", "url": "https://docs.example.com/mcp", **overrides}


class TestSecretsNeverLeave:
    def test_environment_values_are_dropped_and_only_names_remain(self) -> None:
        cfg = _stdio(extra_params={"env": {"API_KEY": "sk-live-real-value", "REGION": "eu"}}, required_secrets=["TOKEN"])

        server = connector_from_config(cfg).server

        assert server is not None
        assert server.env_key_names == ["TOKEN", "API_KEY", "REGION"]
        assert set(server.raw_env.values()) == {""}

    def test_literal_header_values_become_placeholders_and_references_are_kept(self) -> None:
        cfg = _remote(headers={"Authorization": "Bearer live-token", "X-Team": "{{secret:TEAM_ID}}"})

        server = connector_from_config(cfg).server

        assert server is not None
        assert server.headers == {"Authorization": "{{secret:Authorization}}", "X-Team": "{{secret:TEAM_ID}}"}
        assert secret_names_of(server) == ["Authorization", "TEAM_ID"]

    @pytest.mark.parametrize(
        "cfg",
        [
            _remote(url="https://user:hunter2@docs.example.com/mcp"),
            _remote(url="https://docs.example.com/mcp?token=sk-abcdefghijklmnopqrstuvwxyz123456"),
            _stdio(args=["--api-key=sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"]),
        ],
    )
    def test_credentials_inside_the_declaration_keep_the_connector_out(self, cfg: dict[str, object]) -> None:
        outcome = connector_from_config(cfg)

        assert outcome.server is None
        assert outcome.omit is Omit.CONNECTOR_SECRET_MATERIAL


class TestOnlyPortableLaunchesTravel:
    @pytest.mark.parametrize(
        "cfg",
        [
            _stdio(command="/usr/local/bin/mcp-sqlite", args=[]),
            _stdio(args=["mcp-server-sqlite", "/Users/alice/data.db"]),
            _stdio(args=["mcp-server-sqlite", "--db=/Users/alice/data.db"]),
            _stdio(args=["mcp-server-sqlite", "~/data.db"]),
            _stdio(args=["mcp-server-sqlite", "C:\\data\\x.db"]),
            _stdio(command="./server", args=[]),
            _stdio(extra_params={"cwd": "/srv/project"}),
            _stdio(command="python", args=["server.py"]),
        ],
    )
    def test_local_paths_are_not_shared(self, cfg: dict[str, object]) -> None:
        outcome = connector_from_config(cfg)

        assert outcome.server is None
        assert outcome.omit is Omit.CONNECTOR_LOCAL_PATH

    def test_files_bundled_by_another_package_are_not_shared(self) -> None:
        cfg = _stdio(extra_params={"plugin_root": "/data/plugins/x", "data_root": "/data/plugins/x_data"})

        assert connector_from_config(cfg).omit is Omit.CONNECTOR_BUNDLED_FILES

    def test_package_runners_are_portable(self) -> None:
        cfg = _stdio(command="npx", args=["-y", "@modelcontextprotocol/server-memory"])

        server = connector_from_config(cfg).server

        assert server is not None
        assert (server.command, server.args) == ("npx", ["-y", "@modelcontextprotocol/server-memory"])


class TestShape:
    def test_remote_connector_carries_only_url_and_headers(self) -> None:
        cfg = _remote(command="stale", args=["x"], extra_params={"env": {"A": "1"}, "cwd": "/tmp"})

        server = connector_from_config(cfg).server

        assert server is not None
        assert (server.server_type, server.url) == ("streamable_http", "https://docs.example.com/mcp")
        assert (server.command, server.args, server.cwd, server.env_key_names, server.raw_env) == (None, None, None, [], {})

    def test_stdio_connector_carries_no_url_or_headers(self) -> None:
        server = connector_from_config(_stdio(url="https://stale.example", headers={"A": "b"})).server

        assert server is not None
        assert (server.url, server.headers) == (None, None)

    @pytest.mark.parametrize(
        ("raw_type", "expected"),
        [("streamable-http", "streamable_http"), ("http", "streamable_http"), ("sse", "sse")],
    )
    def test_transport_spellings_are_normalized(self, raw_type: str, expected: str) -> None:
        server = connector_from_config(_remote(type=raw_type)).server

        assert server is not None and server.server_type == expected

    def test_missing_transport_is_inferred_like_the_runtime_does(self) -> None:
        assert connector_from_config({"name": "a", "command": "uvx", "args": ["x"]}).server is not None
        sse = connector_from_config({"name": "b", "url": "https://x.example/events"}).server
        http = connector_from_config({"name": "c", "url": "https://x.example/mcp"}).server
        assert sse is not None and sse.server_type == "sse"
        assert http is not None and http.server_type == "streamable_http"

    @pytest.mark.parametrize(
        "cfg",
        [
            {"name": "", "type": "stdio", "command": "uvx"},
            {"name": "x", "type": "websocket", "url": "wss://x.example"},
            {"name": "x", "type": "stdio"},
            {"name": "x", "type": "sse", "url": "ftp://x.example"},
            {"name": "x"},
        ],
    )
    def test_unusable_entries_are_reported_not_guessed(self, cfg: dict[str, object]) -> None:
        outcome = connector_from_config(cfg)

        assert outcome.server is None
        assert outcome.omit is Omit.CONNECTOR_UNSUPPORTED
