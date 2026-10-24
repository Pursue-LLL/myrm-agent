"""Tests for CORS origin parsing and validation."""

from __future__ import annotations

import pytest

from app.core.infra.cors_validator import (
    ALLOWED_SCHEMES,
    CORS_ORIGINS_DEFAULT,
    DESKTOP_FRONTEND_PORT_ENV,
    CORSConfigError,
    parse_and_validate_cors_origins,
    resolve_cors_origins,
)


class TestParseAndValidateCorsOrigins:
    """Tests for parse_and_validate_cors_origins function."""

    def test_single_origin(self) -> None:
        result = parse_and_validate_cors_origins("http://localhost:3000")
        assert result == ["http://localhost:3000"]

    def test_multiple_origins(self) -> None:
        result = parse_and_validate_cors_origins("http://localhost:3000,http://localhost:3001,tauri://localhost")
        assert result == ["http://localhost:3000", "http://localhost:3001", "tauri://localhost"]

    def test_strips_whitespace(self) -> None:
        result = parse_and_validate_cors_origins("  http://localhost:3000 , http://localhost:3001  ")
        assert result == ["http://localhost:3000", "http://localhost:3001"]

    def test_filters_empty_entries(self) -> None:
        result = parse_and_validate_cors_origins("http://localhost:3000,,http://localhost:3001,")
        assert result == ["http://localhost:3000", "http://localhost:3001"]

    def test_https_origin_accepted(self) -> None:
        result = parse_and_validate_cors_origins("https://app.example.com")
        assert result == ["https://app.example.com"]

    def test_tauri_origin_accepted(self) -> None:
        result = parse_and_validate_cors_origins("tauri://localhost")
        assert result == ["tauri://localhost"]

    def test_empty_string_raises(self) -> None:
        with pytest.raises(CORSConfigError, match="cannot be empty"):
            parse_and_validate_cors_origins("")

    def test_only_whitespace_raises(self) -> None:
        with pytest.raises(CORSConfigError, match="cannot be empty"):
            parse_and_validate_cors_origins("   ,  , ")

    def test_wildcard_rejected(self) -> None:
        with pytest.raises(CORSConfigError, match="Invalid CORS origin scheme"):
            parse_and_validate_cors_origins("*")

    def test_invalid_scheme_rejected(self) -> None:
        with pytest.raises(CORSConfigError, match="Invalid CORS origin scheme"):
            parse_and_validate_cors_origins("ftp://files.example.com")

    def test_missing_host_rejected(self) -> None:
        with pytest.raises(CORSConfigError, match="missing host"):
            parse_and_validate_cors_origins("http://")

    def test_mixed_valid_and_invalid_rejects_all(self) -> None:
        with pytest.raises(CORSConfigError):
            parse_and_validate_cors_origins("http://localhost:3000,invalid-origin")

    def test_default_origins_valid(self) -> None:
        result = parse_and_validate_cors_origins(CORS_ORIGINS_DEFAULT)
        assert len(result) == 5
        assert "http://localhost:3000" in result
        assert "tauri://localhost" in result


class TestConstants:
    """Tests for module-level constants."""

    def test_allowed_schemes_is_frozenset(self) -> None:
        assert isinstance(ALLOWED_SCHEMES, frozenset)

    def test_allowed_schemes_contains_expected(self) -> None:
        assert "http://" in ALLOWED_SCHEMES
        assert "https://" in ALLOWED_SCHEMES
        assert "tauri://" in ALLOWED_SCHEMES

    def test_cors_origins_default_not_empty(self) -> None:
        assert len(CORS_ORIGINS_DEFAULT) > 0


class TestResolveCorsOrigins:
    """The desktop shell's own frontend origin must always be allowlisted."""

    def test_missing_port_leaves_origins_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(DESKTOP_FRONTEND_PORT_ENV, raising=False)

        assert resolve_cors_origins(CORS_ORIGINS_DEFAULT) == parse_and_validate_cors_origins(CORS_ORIGINS_DEFAULT)

    def test_desktop_port_appends_loopback_origins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DESKTOP_FRONTEND_PORT_ENV, "13000")

        origins = resolve_cors_origins(CORS_ORIGINS_DEFAULT)

        assert "http://127.0.0.1:13000" in origins
        assert "http://localhost:13000" in origins

    def test_duplicate_origin_is_not_added_twice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(DESKTOP_FRONTEND_PORT_ENV, "3000")

        origins = resolve_cors_origins(CORS_ORIGINS_DEFAULT)

        assert origins.count("http://127.0.0.1:3000") == 1
        assert origins.count("http://localhost:3000") == 1

    @pytest.mark.parametrize("value", ["not-a-port", "0", "70000", "-1"])
    def test_invalid_port_is_ignored(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv(DESKTOP_FRONTEND_PORT_ENV, value)

        assert resolve_cors_origins(CORS_ORIGINS_DEFAULT) == parse_and_validate_cors_origins(CORS_ORIGINS_DEFAULT)
