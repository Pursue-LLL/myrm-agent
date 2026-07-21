"""Unit tests for the business-layer ``MCPServerConfig`` (TLS validation + camelCase round-trip)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.types import MCPServerConfig


class TestTransportValidation:
    def test_sse_requires_url(self) -> None:
        with pytest.raises(ValidationError, match="requires 'url'"):
            MCPServerConfig(name="s", type="sse")

    def test_stdio_requires_command(self) -> None:
        with pytest.raises(ValidationError, match="requires 'command'"):
            MCPServerConfig(name="s", type="stdio")


class TestTLSValidation:
    def test_client_key_requires_cert(self) -> None:
        with pytest.raises(ValidationError, match=r"client_key.*requires.*client_cert"):
            MCPServerConfig(name="s", type="sse", url="https://x", client_key="/k.pem")

    def test_password_requires_cert(self) -> None:
        with pytest.raises(ValidationError, match=r"client_key_password.*requires.*client_cert"):
            MCPServerConfig(name="s", type="sse", url="https://x", client_key_password="pw")


class TestCamelCaseRoundTrip:
    """The frontend sends camelCase; the field must survive dump/validate round-trips."""

    def test_parses_camel_case_alias(self) -> None:
        cfg = MCPServerConfig.model_validate(
            {
                "name": "tls",
                "type": "streamable_http",
                "url": "https://x/mcp",
                "clientCert": "/c.pem",
                "clientKey": "/k.pem",
                "clientKeyPassword": "s3cr3t",
                "sslVerify": "/ca.pem",
                "hostSerial": True,
                "keepaliveInterval": 45,
            }
        )
        assert cfg.client_cert == "/c.pem"
        assert cfg.client_key == "/k.pem"
        assert cfg.client_key_password == "s3cr3t"
        assert cfg.ssl_verify == "/ca.pem"
        assert cfg.host_serial is True
        assert cfg.keepalive_interval == 45

    def test_parses_snake_case_field_name(self) -> None:
        cfg = MCPServerConfig.model_validate(
            {
                "name": "tls",
                "type": "sse",
                "url": "https://x/sse",
                "client_cert": "/c.pem",
                "client_key_password": "pw",
            }
        )
        assert cfg.client_key_password == "pw"

    def test_dump_validate_preserves_passphrase(self) -> None:
        original = MCPServerConfig(
            name="tls",
            type="sse",
            url="https://x/sse",
            client_cert="/c.pem",
            client_key_password="pw",
        )
        payload = original.model_dump(by_alias=True)
        assert payload["clientKeyPassword"] == "pw"
        restored = MCPServerConfig.model_validate(payload)
        assert restored.client_key_password == "pw"

    def test_host_serial_defaults_false(self) -> None:
        cfg = MCPServerConfig(name="s", type="stdio", command="npx")
        assert cfg.host_serial is False

    def test_keepalive_interval_defaults_none(self) -> None:
        cfg = MCPServerConfig(name="s", type="stdio", command="npx")
        assert cfg.keepalive_interval is None
