"""Unit tests for Feishu app_id validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.channels.providers.feishu.channel import FeishuChannel
from app.channels.security.errors import WebhookResponseError


@pytest.fixture
def channel():
    """Create a FeishuChannel instance for testing."""
    return FeishuChannel(
        app_id="cli_test123",
        app_secret="secret_test456",
        verification_token="test_token",
    )


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request object."""
    request = MagicMock()
    request.state._webhook_trace_id = "trace_test_id"
    return request


class TestAppIdValidation:
    """Test app_id validation in verify() method."""

    @pytest.mark.asyncio
    async def test_app_id_match_pass(self, channel: FeishuChannel, mock_request: MagicMock) -> None:
        """Test that matching app_id passes validation."""
        body = json.dumps(
            {
                "header": {"app_id": "cli_test123", "event_type": "im.message.receive_v1"},
                "token": "test_token",
            }
        ).encode()

        await channel.verify(mock_request, body)

    @pytest.mark.asyncio
    async def test_app_id_mismatch_403(self, channel: FeishuChannel, mock_request: MagicMock) -> None:
        """Test that mismatched app_id raises 403 error."""
        body = json.dumps(
            {
                "header": {"app_id": "cli_wrong456", "event_type": "im.message.receive_v1"},
                "token": "test_token",
            }
        ).encode()

        with pytest.raises(WebhookResponseError) as exc_info:
            await channel.verify(mock_request, body)

        assert exc_info.value.status_code == 403
        assert exc_info.value.error_type == "app-id-mismatch"
        assert "cli_test123" in exc_info.value.detail
        assert "cli_wrong456" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_app_id_empty_in_payload_pass(self, channel: FeishuChannel, mock_request: MagicMock) -> None:
        """Test that empty app_id in payload passes (no validation triggered)."""
        body = json.dumps(
            {
                "header": {"app_id": "", "event_type": "im.message.receive_v1"},
                "token": "test_token",
            }
        ).encode()

        await channel.verify(mock_request, body)

    @pytest.mark.asyncio
    async def test_header_missing_pass(self, channel: FeishuChannel, mock_request: MagicMock) -> None:
        """Test that missing header passes (no app_id to validate)."""
        body = json.dumps(
            {
                "token": "test_token",
            }
        ).encode()

        await channel.verify(mock_request, body)

    @pytest.mark.asyncio
    async def test_challenge_skip_validation(self, channel: FeishuChannel, mock_request: MagicMock) -> None:
        """Test that challenge requests skip all validation."""
        body = json.dumps(
            {
                "challenge": "test_challenge_code",
                "header": {"app_id": "cli_wrong456"},
            }
        ).encode()

        await channel.verify(mock_request, body)


class TestInitValidation:
    """Test __init__() parameter validation."""

    def test_init_empty_app_id_raises(self) -> None:
        """Test that empty app_id raises ValueError."""
        with pytest.raises(ValueError, match="app_id cannot be empty"):
            FeishuChannel(app_id="", app_secret="secret_test")

    def test_init_whitespace_app_id_raises(self) -> None:
        """Test that whitespace-only app_id raises ValueError."""
        with pytest.raises(ValueError, match="app_id cannot be empty"):
            FeishuChannel(app_id="   ", app_secret="secret_test")

    def test_init_empty_app_secret_raises(self) -> None:
        """Test that empty app_secret raises ValueError."""
        with pytest.raises(ValueError, match="app_secret cannot be empty"):
            FeishuChannel(app_id="cli_test", app_secret="")

    def test_init_valid_params_pass(self) -> None:
        """Test that valid params pass initialization."""
        channel = FeishuChannel(app_id="cli_test", app_secret="secret_test")
        assert channel._app_id == "cli_test"
        assert channel._app_secret == "secret_test"
