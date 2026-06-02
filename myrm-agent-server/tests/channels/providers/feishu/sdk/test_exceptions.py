"""Tests for feishu SDK exceptions — independent hierarchy."""

from __future__ import annotations

import pytest

from app.channels.providers.feishu.sdk.exceptions import (
    FeishuAPIError,
    FeishuAuthError,
    FeishuRateLimitError,
    FeishuSendError,
)


class TestExceptionHierarchy:
    """Verify Feishu exception hierarchy and attributes."""

    def test_feishu_api_error_is_exception(self) -> None:
        exc = FeishuAPIError("test")
        assert isinstance(exc, Exception)
        assert str(exc) == "test"

    def test_feishu_send_error_inherits_api_error(self) -> None:
        exc = FeishuSendError("test", status_code=400, retriable=False)
        assert isinstance(exc, FeishuAPIError)
        assert exc.status_code == 400
        assert exc.retriable is False

    def test_feishu_rate_limit_inherits_send_error(self) -> None:
        exc = FeishuRateLimitError("rate limited", retry_after=2.5)
        assert isinstance(exc, FeishuSendError)
        assert isinstance(exc, FeishuAPIError)
        assert exc.retry_after == 2.5
        assert exc.status_code == 429
        assert exc.retriable is True

    def test_feishu_auth_error_inherits_api_error(self) -> None:
        exc = FeishuAuthError("invalid creds")
        assert isinstance(exc, FeishuAPIError)

    def test_catch_by_api_error(self) -> None:
        with pytest.raises(FeishuAPIError):
            raise FeishuSendError("fail", status_code=500)

    def test_catch_auth_by_api_error(self) -> None:
        with pytest.raises(FeishuAPIError):
            raise FeishuAuthError("expired")

    def test_catch_rate_limit_by_send_error(self) -> None:
        with pytest.raises(FeishuSendError):
            raise FeishuRateLimitError("too fast")

    def test_send_error_defaults(self) -> None:
        exc = FeishuSendError("msg")
        assert exc.status_code == 0
        assert exc.retriable is True

    def test_rate_limit_defaults(self) -> None:
        exc = FeishuRateLimitError("msg")
        assert exc.retry_after == 1.0
        assert exc.status_code == 429
