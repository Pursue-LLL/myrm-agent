"""Tests for WeChat API error hint helpers."""

from __future__ import annotations

from app.channels.providers.wechat.wechat_api_errors import (
    format_wechat_api_error_message,
    resolve_wechat_api_locale,
)


def test_resolve_wechat_api_locale_defaults_and_prefixes() -> None:
    assert resolve_wechat_api_locale(None) == "zh"
    assert resolve_wechat_api_locale("") == "zh"
    assert resolve_wechat_api_locale("zh-CN") == "zh"
    assert resolve_wechat_api_locale("en-US") == "en"


def test_format_wechat_api_error_message_unknown_errcode_without_errmsg() -> None:
    message = format_wechat_api_error_message(99999, "", path="draft/add", locale="en")
    assert "WeChat API error on draft/add" in message
    assert "errcode=99999" in message


def test_format_wechat_api_error_message_unknown_errcode_with_errmsg() -> None:
    message = format_wechat_api_error_message(
        99999,
        "custom failure",
        path="media/upload",
        locale="zh",
    )
    assert "custom failure" in message
    assert "errcode=99999" in message
