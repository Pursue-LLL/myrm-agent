"""Tests for path_component.py (identifier-to-directory-name validation)."""

from __future__ import annotations

from myrm_agent_harness.toolkits.code_execution.security.path_component import (
    is_path_component_safe,
    validate_path_component,
)


class TestValidatePathComponent:
    def test_valid_component(self) -> None:
        result = validate_path_component("user-123")
        assert result.is_safe is True

    def test_empty_component(self) -> None:
        result = validate_path_component("")
        assert result.is_safe is False

    def test_too_long(self) -> None:
        result = validate_path_component("a" * 256)
        assert result.is_safe is False

    def test_starts_with_dot(self) -> None:
        result = validate_path_component(".hidden")
        assert result.is_safe is False

    def test_contains_dotdot(self) -> None:
        result = validate_path_component("foo..bar")
        assert result.is_safe is False

    def test_contains_slash(self) -> None:
        result = validate_path_component("foo/bar")
        assert result.is_safe is False

    def test_contains_backslash(self) -> None:
        result = validate_path_component("foo\\bar")
        assert result.is_safe is False

    def test_special_chars(self) -> None:
        result = validate_path_component("foo@bar")
        assert result.is_safe is False

    def test_alphanumeric_hyphen_underscore(self) -> None:
        result = validate_path_component("valid_user-name123")
        assert result.is_safe is True

    def test_is_path_component_safe_convenience(self) -> None:
        assert is_path_component_safe("abc123") is True
        assert is_path_component_safe("") is False
