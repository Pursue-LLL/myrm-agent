"""Unit tests for Feishu app_id validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.channels.core.factory import create_channels
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


class TestUnconfiguredChannel:
    """A channel without app credentials exists, is inert, and refuses webhooks."""

    @pytest.mark.parametrize(
        ("app_id", "app_secret"),
        [("", ""), ("   ", "secret_test"), ("cli_test", ""), ("cli_test", "  ")],
    )
    def test_blank_credentials_construct_as_unconfigured(self, app_id: str, app_secret: str) -> None:
        channel = FeishuChannel(app_id=app_id, app_secret=app_secret)
        assert channel._client.is_configured is False

    def test_from_credentials_without_any_value_constructs(self) -> None:
        channel = FeishuChannel.from_credentials({})
        assert channel._client.is_configured is False

    @pytest.mark.asyncio
    async def test_factory_creates_it_from_an_empty_store(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Settings lists a channel only if the gateway holds an instance of it, so the factory
        # must not drop Feishu when nothing is stored yet.
        for variable in ("FEISHU_APP_ID", "FEISHU_APP_SECRET"):
            monkeypatch.delenv(variable, raising=False)

        async def empty_source(_config_key: str) -> dict[str, object]:
            return {}

        channels = await create_channels(empty_source, names=frozenset({"feishu"}), skip_empty=False)

        channel = channels["feishu"]
        assert isinstance(channel, FeishuChannel)
        assert channel._client.is_configured is False

    def test_credentials_are_stripped(self) -> None:
        channel = FeishuChannel(app_id=" cli_test ", app_secret=" secret_test ")
        assert channel._app_id == "cli_test"
        assert channel._app_secret == "secret_test"
        assert channel._client.is_configured is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "payload",
        [
            {"challenge": "c", "header": {"app_id": "cli_any"}},
            {"header": {"event_type": "im.message.receive_v1"}},
            {},
        ],
    )
    async def test_webhook_is_refused_even_without_a_token(self, mock_request: MagicMock, payload: dict[str, object]) -> None:
        channel = FeishuChannel(app_id="", app_secret="")

        with pytest.raises(WebhookResponseError) as exc_info:
            await channel.verify(mock_request, json.dumps(payload).encode())

        assert exc_info.value.status_code == 503
        assert exc_info.value.error_type == "channel-not-configured"
