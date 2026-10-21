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

    @pytest.mark.parametrize("status", [408, 425, 429, 500, 502, 503])
    def test_transient_http_status_may_be_retried(self, status: int) -> None:
        err = ChannelSendError.from_http_status("line", status)
        assert (err.retriable, err.status_code, err.accepted) == (True, status, False)

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 413])
    def test_other_client_errors_never_succeed_on_resend(self, status: int) -> None:
        assert ChannelSendError.from_http_status("line", status).retriable is False

    def test_http_status_error_names_channel_status_and_trimmed_detail(self) -> None:
        err = ChannelSendError.from_http_status("line", 400, "x" * 500)
        assert err.channel == "line"
        assert str(err).startswith("line rejected the message (HTTP 400): xxx")
        assert len(str(err)) < 260

    def test_attachment_failure_after_delivered_text_is_partial_and_never_retried(self) -> None:
        err = ChannelSendError.for_attachments("slack", ["a.pdf", "b.pdf"], delivered_any=True)
        assert (err.accepted, err.retriable) == (True, False)
        assert err.failed_attachments == ("a.pdf", "b.pdf")

    def test_attachment_failure_with_nothing_delivered_may_be_retried(self) -> None:
        err = ChannelSendError.for_attachments("slack", ["a.pdf"], delivered_any=False)
        assert (err.accepted, err.retriable) == (False, True)

    def test_permanent_attachment_failure_is_not_retried(self) -> None:
        err = ChannelSendError.for_attachments("slack", ["a.pdf"], delivered_any=False, retriable=False)
        assert err.retriable is False


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
