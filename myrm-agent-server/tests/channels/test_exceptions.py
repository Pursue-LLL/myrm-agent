"""Tests for channel exception hierarchy."""

import pytest

from app.channels.core.exceptions import (
    ChannelAuthError,
    ChannelConnectionError,
    ChannelError,
    ChannelSendError,
    RateLimitError,
)


class TestChannelErrorHierarchy:
    def test_channel_error_is_exception(self) -> None:
        assert issubclass(ChannelError, Exception)

    def test_send_error_inherits_channel_error(self) -> None:
        assert issubclass(ChannelSendError, ChannelError)

    def test_rate_limit_inherits_send_error(self) -> None:
        assert issubclass(RateLimitError, ChannelSendError)

    def test_auth_error_inherits_channel_error(self) -> None:
        assert issubclass(ChannelAuthError, ChannelError)

    def test_connection_error_inherits_channel_error(self) -> None:
        assert issubclass(ChannelConnectionError, ChannelError)


class TestChannelError:
    def test_message_and_channel(self) -> None:
        err = ChannelError("boom", channel="telegram")
        assert str(err) == "boom"
        assert err.channel == "telegram"

    def test_default_channel_empty(self) -> None:
        err = ChannelError("fail")
        assert err.channel == ""


class TestChannelSendError:
    def test_attributes(self) -> None:
        err = ChannelSendError("send failed", channel="slack", status_code=500, retriable=False)
        assert err.status_code == 500
        assert err.retriable is False
        assert err.channel == "slack"

    def test_defaults(self) -> None:
        err = ChannelSendError("fail")
        assert err.status_code == 0
        assert err.retriable is True

    def test_catchable_as_channel_error(self) -> None:
        with pytest.raises(ChannelError):
            raise ChannelSendError("fail")


class TestRateLimitError:
    def test_retry_after(self) -> None:
        err = RateLimitError("rate limited", retry_after=5.0, channel="discord")
        assert err.retry_after == 5.0
        assert err.status_code == 429
        assert err.retriable is True
        assert err.channel == "discord"

    def test_defaults(self) -> None:
        err = RateLimitError("limited")
        assert err.retry_after == 1.0
        assert err.status_code == 429

    def test_catchable_as_send_error(self) -> None:
        with pytest.raises(ChannelSendError):
            raise RateLimitError("limited")


class TestChannelAuthError:
    def test_attributes(self) -> None:
        err = ChannelAuthError("bad token", channel="feishu")
        assert str(err) == "bad token"
        assert err.channel == "feishu"


class TestChannelConnectionError:
    def test_attributes(self) -> None:
        err = ChannelConnectionError("timeout", channel="matrix")
        assert str(err) == "timeout"
        assert err.channel == "matrix"
