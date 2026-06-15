"""Unit tests for business-layer config validators (ModelConfig + MCPServerConfig).

Covers field_validator auto-healing: whitespace stripping, trailing slash removal,
empty-to-None normalization.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.types import MCPServerConfig, ModelConfig


class TestModelConfigValidators:
    """Tests for ModelConfig._strip_whitespace and _normalize_base_url."""

    def test_model_strip_whitespace(self) -> None:
        c = ModelConfig(model="  gpt-4  ", api_key="key")
        assert c.model == "gpt-4"

    def test_api_key_strip_whitespace(self) -> None:
        c = ModelConfig(model="gpt-4", api_key="  sk-abc123  ")
        assert c.api_key == "sk-abc123"

    def test_base_url_strip_trailing_slash(self) -> None:
        c = ModelConfig(model="m", api_key="k", base_url="https://api.openai.com/v1/")
        assert c.base_url == "https://api.openai.com/v1"

    def test_base_url_strip_multiple_trailing_slashes(self) -> None:
        c = ModelConfig(model="m", api_key="k", base_url="https://api.example.com///")
        assert c.base_url == "https://api.example.com"

    def test_base_url_strip_whitespace_and_slash(self) -> None:
        c = ModelConfig(model="m", api_key="k", base_url="  https://api.example.com/  ")
        assert c.base_url == "https://api.example.com"

    def test_base_url_empty_string_becomes_none(self) -> None:
        c = ModelConfig(model="m", api_key="k", base_url="")
        assert c.base_url is None

    def test_base_url_whitespace_only_becomes_none(self) -> None:
        c = ModelConfig(model="m", api_key="k", base_url="   ")
        assert c.base_url is None

    def test_base_url_single_slash_becomes_none(self) -> None:
        c = ModelConfig(model="m", api_key="k", base_url="/")
        assert c.base_url is None

    def test_base_url_none_stays_none(self) -> None:
        c = ModelConfig(model="m", api_key="k", base_url=None)
        assert c.base_url is None

    def test_model_whitespace_only_fails_min_length(self) -> None:
        with pytest.raises(ValidationError):
            ModelConfig(model="   ", api_key="key")

    def test_api_key_whitespace_only_fails_min_length(self) -> None:
        with pytest.raises(ValidationError):
            ModelConfig(model="gpt-4", api_key="   ")

    def test_camel_case_base_url_normalized(self) -> None:
        c = ModelConfig.model_validate(
            {"model": "m", "apiKey": "k", "baseUrl": "https://api.example.com/v1/"}
        )
        assert c.base_url == "https://api.example.com/v1"


class TestMCPServerConfigUrlValidator:
    """Tests for MCPServerConfig._normalize_url."""

    def test_url_strip_trailing_slash(self) -> None:
        c = MCPServerConfig(name="s", type="sse", url="https://mcp.example.com/")
        assert c.url == "https://mcp.example.com"

    def test_url_strip_whitespace_and_slash(self) -> None:
        c = MCPServerConfig(name="s", type="sse", url="  https://mcp.example.com/  ")
        assert c.url == "https://mcp.example.com"

    def test_url_empty_string_becomes_none(self) -> None:
        c = MCPServerConfig(name="s", type="stdio", command="npx", url="")
        assert c.url is None

    def test_url_none_stays_none(self) -> None:
        c = MCPServerConfig(name="s", type="stdio", command="npx", url=None)
        assert c.url is None

    def test_url_whitespace_only_becomes_none(self) -> None:
        c = MCPServerConfig(name="s", type="stdio", command="npx", url="   ")
        assert c.url is None
