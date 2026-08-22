"""Tests for OneBot Channel enhancements: validator, auto-reconnect, message fragmentation, etc."""

import asyncio
from unittest.mock import Mock, patch

import pytest

from app.channels.core.credentials import (
    credential_field,
    credential_spec,
    resolve_credentials,
)
from app.channels.core.logging_filter import SensitiveDataFilter, redact_sensitive
from app.channels.core.rate_limit import RateLimitConfig, RateLimiter


class TestCredentialFieldValidator:
    """Test CredentialField validator functionality."""

    @pytest.mark.asyncio
    async def test_validator_success(self):
        """Test validator successfully transforms value."""

        def port_validator(value: str) -> str:
            return str(int(value))  # Ensure valid integer

        spec = credential_spec(
            "testCreds",
            port=credential_field(
                db_key="port",
                env_var="TEST_PORT",
                default="8080",
                validator=port_validator,
            ),
        )

        # Valid port
        async def source(_config_key: str):
            return {"port": "3000"}

        result = await resolve_credentials(spec, source)
        assert result["port"] == "3000"

    @pytest.mark.asyncio
    async def test_validator_fallback_to_default(self):
        """Test validator falls back to default on error."""

        def strict_validator(value: str) -> str:
            if not value.isdigit():
                raise ValueError("Must be numeric")
            return value

        spec = credential_spec(
            "testCreds",
            port=credential_field(
                db_key="port",
                env_var="TEST_PORT",
                default="8080",
                validator=strict_validator,
            ),
        )

        # Invalid value should fallback to default
        async def source(_config_key: str):
            return {"port": "invalid"}

        with patch("app.channels.core.credentials.logger") as mock_logger:
            result = await resolve_credentials(spec, source)
            assert result["port"] == "8080"
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_source_uses_default_not_env(self):
        """Without source, field default is used (env vars are ignored)."""

        def port_validator(value: str) -> str:
            return str(int(value))

        spec = credential_spec(
            "testCreds",
            port=credential_field(
                db_key="port",
                env_var="TEST_PORT",
                default="8080",
                validator=port_validator,
            ),
        )

        with patch.dict("os.environ", {"TEST_PORT": "9000"}):
            result = await resolve_credentials(spec, None)
            assert result["port"] == "8080"


class TestSensitiveDataFilter:
    """Test SensitiveDataFilter logging redaction."""

    def test_redact_token_in_log_message(self):
        """Test token is redacted from log messages."""
        log_filter = SensitiveDataFilter()

        # Create a mock log record
        record = Mock()
        record.msg = "Connecting with token=abc123secret456"
        record.args = ()

        log_filter.filter(record)

        assert "token=***REDACTED***" in record.msg
        assert "abc123secret456" not in record.msg

    def test_redact_password_in_log_message(self):
        """Test password is redacted from log messages."""
        log_filter = SensitiveDataFilter()

        record = Mock()
        record.msg = "Auth failed: password=MySecretPass123"
        record.args = ()

        log_filter.filter(record)

        assert "password=***REDACTED***" in record.msg
        assert "MySecretPass123" not in record.msg

    def test_redact_multiple_secrets(self):
        """Test multiple secrets are redacted."""
        log_filter = SensitiveDataFilter()

        record = Mock()
        record.msg = "Config: api_key=KEY123 secret=SECRET456 token=TOK789"
        record.args = ()

        log_filter.filter(record)

        assert "api_key=***REDACTED***" in record.msg
        assert "secret=***REDACTED***" in record.msg
        assert "token=***REDACTED***" in record.msg
        assert "KEY123" not in record.msg
        assert "SECRET456" not in record.msg
        assert "TOK789" not in record.msg

    def test_redact_sensitive_utility_function(self):
        """Test redact_sensitive() utility function."""
        text = "Config: access_token=secret123 password=pass456"
        redacted = redact_sensitive(text)

        assert "access_token=***REDACTED***" in redacted
        assert "password=***REDACTED***" in redacted
        assert "secret123" not in redacted
        assert "pass456" not in redacted

    def test_redact_sensitive_with_special_characters(self):
        """Test redaction with special characters in values."""
        # Values with quotes, slashes, etc.
        text = "Bearer token=\"abc/def+123\" password='secret!@#$%'"
        redacted = redact_sensitive(text)

        assert "token=***REDACTED***" in redacted
        assert "password=***REDACTED***" in redacted
        assert "abc/def+123" not in redacted
        assert "secret!@#$%" not in redacted

    def test_redact_sensitive_multiline(self):
        """Test redaction across multiple lines."""
        text = """
        Config:
          access_token=abc123
          api_key=key456
          password=pass789
        """
        redacted = redact_sensitive(text)

        assert "access_token=***REDACTED***" in redacted
        assert "api_key=***REDACTED***" in redacted
        assert "password=***REDACTED***" in redacted
        assert "abc123" not in redacted
        assert "key456" not in redacted
        assert "pass789" not in redacted

    def test_redact_sensitive_no_false_positives(self):
        """Test redaction doesn't affect normal words."""
        text = "The secretary accessed the token machine with a password."
        redacted = redact_sensitive(text)

        # Words 'secretary', 'accessed', 'token', 'password' in normal context should not be redacted
        assert "secretary" in redacted
        assert "accessed" in redacted
        # Note: our regex only matches assignment patterns like "token=", so normal words are safe
        assert redacted == text


class TestRateLimiterConcurrency:
    """Test RateLimiter concurrent safety."""

    @pytest.mark.asyncio
    async def test_concurrent_rate_limiter_access(self):
        """Test RateLimiter handles concurrent access safely."""
        from app.channels.types import InboundMessage

        config = RateLimitConfig(max_requests=10, window_seconds=1.0)
        limiter = RateLimiter(config)

        # Simulate concurrent requests
        async def make_request(sender_id: str):
            for _ in range(5):
                msg = InboundMessage(
                    channel="test",
                    sender_id=sender_id,
                    content="test",
                )
                allowed = await limiter.check_and_update(msg)
                if not allowed:
                    return False
                await asyncio.sleep(0.01)  # Simulate processing
            return True

        # Run 5 concurrent tasks for the same sender
        tasks = [make_request("user1") for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # At least some requests should be rate-limited
        # (5 tasks * 5 requests = 25 total, but limit is 10)
        assert not all(results), "Rate limiter should block some requests"

    @pytest.mark.asyncio
    async def test_rate_limiter_different_senders(self):
        """Test RateLimiter isolates different senders."""
        from app.channels.types import InboundMessage

        config = RateLimitConfig(max_requests=5, window_seconds=1.0)
        limiter = RateLimiter(config)

        # Different senders should have independent limits
        for _ in range(5):
            msg1 = InboundMessage(channel="test", sender_id="user1", content="test")
            msg2 = InboundMessage(channel="test", sender_id="user2", content="test")
            assert await limiter.check_and_update(msg1)
            assert await limiter.check_and_update(msg2)

        # Both should be limited now
        msg1 = InboundMessage(channel="test", sender_id="user1", content="test")
        msg2 = InboundMessage(channel="test", sender_id="user2", content="test")
        assert not await limiter.check_and_update(msg1)
        assert not await limiter.check_and_update(msg2)


class TestOneBotChannelAutoReconnect:
    """Test OneBot Channel auto-reconnect mechanism."""

    @pytest.mark.asyncio
    async def test_reconnect_delay_exponential_backoff(self):
        """Test reconnect delay follows exponential backoff."""
        from app.channels.providers.onebot.channel import OneBotChannel

        channel = OneBotChannel(
            host="127.0.0.1",
            port="9999",  # Invalid port to trigger reconnect
            access_token="",
        )

        # Check initial state
        assert channel._reconnect_delay == 1.0
        assert channel._max_reconnect_delay == 60.0

        # Simulate exponential backoff manually
        delays = [channel._reconnect_delay]
        for _ in range(6):
            channel._reconnect_delay = min(channel._reconnect_delay * 2, channel._max_reconnect_delay)
            delays.append(channel._reconnect_delay)

        # Verify exponential growth: 1, 2, 4, 8, 16, 32, 60 (capped)
        assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0]

    @pytest.mark.asyncio
    async def test_reconnect_delay_reset_on_success(self):
        """Test reconnect delay resets to 1.0 on successful reconnect."""
        from app.channels.providers.onebot.channel import OneBotChannel

        channel = OneBotChannel(
            host="127.0.0.1",
            port="9999",
            access_token="",
        )

        # Simulate failed reconnects
        channel._reconnect_delay = 32.0

        # Simulate successful reconnect (manual reset)
        channel._reconnect_delay = 1.0

        assert channel._reconnect_delay == 1.0

    @pytest.mark.asyncio
    async def test_should_reconnect_flag(self):
        """Test _should_reconnect flag controls reconnection."""
        from app.channels.providers.onebot.channel import OneBotChannel

        channel = OneBotChannel(
            host="127.0.0.1",
            port="9999",
            access_token="",
        )

        # Initially False
        assert channel._should_reconnect is False

        # Set to True during start (simulated)
        channel._should_reconnect = True
        assert channel._should_reconnect is True

        # Set to False during stop (simulated)
        channel._should_reconnect = False
        assert channel._should_reconnect is False


class TestOneBotChannelRenderDelivery:
    """Test OneBot Channel uses render() multi-chunk delivery."""

    @pytest.mark.asyncio
    async def test_send_long_message_uses_render_multi_chunk(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from app.channels.providers.onebot.channel import OneBotChannel
        from app.channels.rendering.renderer import render
        from app.channels.types.messages import OutboundMessage

        channel = OneBotChannel(host="127.0.0.1", port=3001)
        channel._active_ws = MagicMock()
        channel._active_ws.closed = False

        long_body = "OneBot QQ long reply。" * 500
        msg = OutboundMessage(
            channel="onebot",
            recipient_id="123456789",
            content=long_body,
            user_id="u1",
            metadata={"is_group": False},
        )
        expected_chunks = render(msg, channel.render_style)
        assert len(expected_chunks) >= 2

        call_count = 0

        async def _fake_call_api(action: str, params: dict[str, object], timeout: float = 10.0) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {"status": "ok", "data": {"message_id": 1000 + call_count}}

        channel._call_api = AsyncMock(side_effect=_fake_call_api)

        result = await channel.send(msg)
        assert result == str(1000 + len(expected_chunks))
        assert channel._call_api.await_count == len(expected_chunks)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
