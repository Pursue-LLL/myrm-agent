"""Tests for channel credential schema, resolution, and factory."""

from __future__ import annotations

from typing import Self
from unittest.mock import AsyncMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import (
    ChannelCredentialSpec,
    CredentialSource,
    credential_field,
    credential_spec,
    parse_bool,
    resolve_credentials,
)
from app.channels.core.factory import create_channels
from app.channels.types import OutboundMessage

# ---------------------------------------------------------------------------
# parse_bool
# ---------------------------------------------------------------------------


class TestParseBool:
    @pytest.mark.parametrize("val", ["true", "True", "TRUE", "1", "yes", "Yes", "YES"])
    def test_truthy(self, val: str) -> None:
        assert parse_bool(val) is True

    @pytest.mark.parametrize("val", ["false", "False", "0", "no", "", "anything"])
    def test_falsy(self, val: str) -> None:
        assert parse_bool(val) is False

    def test_whitespace_stripped(self) -> None:
        assert parse_bool("  true  ") is True
        assert parse_bool("  false  ") is False


# ---------------------------------------------------------------------------
# CredentialField / ChannelCredentialSpec
# ---------------------------------------------------------------------------


class TestCredentialTypes:
    def test_credential_field_frozen(self) -> None:
        f = credential_field("key", "ENV_VAR", "default")
        assert f.db_key == "key"
        assert f.env_var == "ENV_VAR"
        assert f.default == "default"
        with pytest.raises(AttributeError):
            f.db_key = "other"  # type: ignore[misc]

    def test_credential_spec_frozen(self) -> None:
        spec = credential_spec(
            "testCreds",
            token=credential_field("token", "TEST_TOKEN"),
        )
        assert spec.config_key == "testCreds"
        assert len(spec.fields) == 1
        assert spec.fields[0][0] == "token"

    def test_default_empty_string(self) -> None:
        f = credential_field("k", "E")
        assert f.default == ""


# ---------------------------------------------------------------------------
# resolve_credentials
# ---------------------------------------------------------------------------


class TestResolveCredentials:
    @pytest.fixture()
    def spec(self) -> ChannelCredentialSpec:
        return credential_spec(
            "testCreds",
            app_id=credential_field("appId", "TEST_APP_ID", ""),
            secret=credential_field("secret", "TEST_SECRET", "default_secret"),
        )

    @pytest.mark.asyncio()
    async def test_no_source_uses_defaults(self, spec: ChannelCredentialSpec) -> None:
        result = await resolve_credentials(spec)
        assert result["app_id"] == ""
        assert result["secret"] == "default_secret"

    @pytest.mark.asyncio()
    async def test_source_full(self, spec: ChannelCredentialSpec) -> None:
        source: CredentialSource = AsyncMock(return_value={"appId": "db_id", "secret": "db_secret"})
        result = await resolve_credentials(spec, source)
        assert result == {"app_id": "db_id", "secret": "db_secret"}

    @pytest.mark.asyncio()
    async def test_partial_source_uses_default_for_missing(self, spec: ChannelCredentialSpec) -> None:
        """DB has app_id but not secret → secret falls back to field default."""
        source: CredentialSource = AsyncMock(return_value={"appId": "db_id"})
        result = await resolve_credentials(spec, source)
        assert result["app_id"] == "db_id"
        assert result["secret"] == "default_secret"

    @pytest.mark.asyncio()
    async def test_partial_source_no_env_fallback(self, spec: ChannelCredentialSpec, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing DB fields do not fall back to environment variables."""
        monkeypatch.setenv("TEST_SECRET", "env_secret")
        source: CredentialSource = AsyncMock(return_value={"appId": "db_id"})
        result = await resolve_credentials(spec, source)
        assert result["app_id"] == "db_id"
        assert result["secret"] == "default_secret"

    @pytest.mark.asyncio()
    async def test_source_returns_none_uses_defaults(self, spec: ChannelCredentialSpec) -> None:
        source: CredentialSource = AsyncMock(return_value=None)
        result = await resolve_credentials(spec, source)
        assert result["app_id"] == ""
        assert result["secret"] == "default_secret"


# ---------------------------------------------------------------------------
# BaseChannel.credential_spec / from_credentials
# ---------------------------------------------------------------------------


class _StubChannel(BaseChannel):
    name = "stub"
    credential_spec = credential_spec(
        "stubCreds",
        token=credential_field("token", "STUB_TOKEN"),
        port=credential_field("port", "STUB_PORT", "8080"),
    )

    def __init__(self, token: str = "", port: str = "8080") -> None:
        super().__init__()
        self.token = token
        self.port = port

    async def send(self, msg: OutboundMessage) -> str | None:
        return None


class _CustomFromCredsChannel(BaseChannel):
    name = "custom"
    credential_spec = credential_spec(
        "customCreds",
        api_key=credential_field("apiKey", "CUSTOM_KEY"),
        use_ssl=credential_field("useSsl", "CUSTOM_SSL", "false"),
    )

    def __init__(self, api_key: str = "", use_ssl: bool = False) -> None:
        super().__init__()
        self.api_key = api_key
        self.use_ssl = use_ssl

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        return cls(
            api_key=creds.get("api_key", ""),
            use_ssl=parse_bool(creds.get("use_ssl", "false")),
        )

    async def send(self, msg: OutboundMessage) -> str | None:
        return None


class TestBaseChannelCredentials:
    def test_default_credential_spec_none(self) -> None:
        assert BaseChannel.credential_spec is None

    def test_stub_credential_spec(self) -> None:
        assert _StubChannel.credential_spec is not None
        assert _StubChannel.credential_spec.config_key == "stubCreds"

    def test_default_from_credentials(self) -> None:
        ch = _StubChannel.from_credentials({"token": "abc", "port": "9090"})
        assert ch.token == "abc"
        assert ch.port == "9090"

    def test_custom_from_credentials_bool(self) -> None:
        ch = _CustomFromCredsChannel.from_credentials({"api_key": "k", "use_ssl": "true"})
        assert ch.api_key == "k"
        assert ch.use_ssl is True

    def test_custom_from_credentials_false(self) -> None:
        ch = _CustomFromCredsChannel.from_credentials({"api_key": "k", "use_ssl": "false"})
        assert ch.use_ssl is False


# ---------------------------------------------------------------------------
# create_channels (factory)
# ---------------------------------------------------------------------------


class TestCreateChannels:
    @pytest.mark.asyncio()
    async def test_skip_empty_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("STUB_TOKEN", raising=False)
        monkeypatch.delenv("STUB_PORT", raising=False)
        monkeypatch.setattr(
            "app.channels.core.factory.registered_names",
            lambda: frozenset({"stub"}),
        )
        monkeypatch.setattr(
            "app.channels.core.factory.get_channel_class_safe",
            lambda name: _StubChannel if name == "stub" else None,
        )
        spec_with_defaults = credential_spec(
            "stubCreds",
            token=credential_field("token", "STUB_TOKEN", ""),
            port=credential_field("port", "STUB_PORT", ""),
        )
        monkeypatch.setattr(_StubChannel, "credential_spec", spec_with_defaults)
        result = await create_channels(skip_empty=True)
        assert "stub" not in result

    @pytest.mark.asyncio()
    async def test_create_with_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.channels.core.factory.registered_names",
            lambda: frozenset({"stub"}),
        )
        monkeypatch.setattr(
            "app.channels.core.factory.get_channel_class_safe",
            lambda name: _StubChannel if name == "stub" else None,
        )
        source: CredentialSource = AsyncMock(return_value={"token": "db_token", "port": "9090"})
        result = await create_channels(source=source)
        assert "stub" in result
        ch = result["stub"]
        assert isinstance(ch, _StubChannel)
        assert ch.token == "db_token"
        assert ch.port == "9090"

    @pytest.mark.asyncio()
    async def test_names_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.channels.core.factory.get_channel_class_safe",
            lambda name: _StubChannel if name == "stub" else None,
        )
        source: CredentialSource = AsyncMock(return_value={"token": "t"})
        result = await create_channels(source=source, names=frozenset({"stub", "nonexistent"}))
        assert "stub" in result
        assert "nonexistent" not in result

    @pytest.mark.asyncio()
    async def test_from_credentials_error_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BadChannel(BaseChannel):
            name = "bad"
            credential_spec = credential_spec("badCreds", x=credential_field("x", "X"))

            @classmethod
            def from_credentials(cls, creds: dict[str, str]) -> Self:
                raise ValueError("boom")

            async def send(self, msg: OutboundMessage) -> str | None:
                return None

        monkeypatch.setattr(
            "app.channels.core.factory.registered_names",
            lambda: frozenset({"bad"}),
        )
        monkeypatch.setattr(
            "app.channels.core.factory.get_channel_class_safe",
            lambda name: _BadChannel if name == "bad" else None,
        )
        source: CredentialSource = AsyncMock(return_value={"x": "val"})
        result = await create_channels(source=source)
        assert "bad" not in result
