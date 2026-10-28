"""Unit tests for the share password-gate page (bilingual copy and the locked-out variant)."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.security.share.share_locale import ShareLang
from app.core.security.share.share_password_page import password_gate_response, render_password_gate_html


def _request(accept_language: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if accept_language is not None:
        headers.append((b"accept-language", accept_language.encode()))
    return Request(scope={"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_plain_gate_page_prompts_for_a_password_in_english_by_default() -> None:
    html = render_password_gate_html()

    assert '<html lang="en">' in html
    assert "<title>Password Required</title>" in html
    assert 'placeholder="Enter password"' in html
    assert ">Unlock</button>" in html
    assert "display:none" in html
    assert 'http-equiv="refresh"' not in html


def test_chinese_gate_page_has_no_english_leftovers() -> None:
    html = render_password_gate_html(lang="zh")

    assert '<html lang="zh-CN">' in html
    assert "<title>需要密码</title>" in html
    assert 'placeholder="输入密码"' in html
    assert ">解锁</button>" in html
    for english in ("Password Required", "Enter password", "Unlock", "password-protected"):
        assert english not in html


@pytest.mark.parametrize(
    ("lang", "message"),
    [("en", "Incorrect password. Please try again."), ("zh", "密码错误，请重试。")],
)
def test_wrong_password_variant_shows_the_error(lang: ShareLang, message: str) -> None:
    html = render_password_gate_html(lang=lang, wrong_password=True)

    assert message in html
    assert "display:block" in html


@pytest.mark.parametrize(
    ("lang", "message"),
    [
        ("en", "Too many incorrect attempts. Try again in 42 seconds."),
        ("zh", "错误次数过多，请 42 秒后重试。"),
    ],
)
def test_locked_variant_disables_the_form_and_reloads_after_the_lock_lifts(lang: ShareLang, message: str) -> None:
    html = render_password_gate_html(lang=lang, retry_after=42)

    assert message in html
    assert "autofocus disabled/>" in html
    assert 'type="submit" disabled>' in html
    assert '<meta http-equiv="refresh" content="43"/>' in html


def test_lock_takes_precedence_over_the_wrong_password_message() -> None:
    html = render_password_gate_html(wrong_password=True, retry_after=5)

    assert "Too many incorrect attempts" in html
    assert "Incorrect password" not in html


def test_gate_response_is_a_403_in_the_visitor_language() -> None:
    english = password_gate_response(_request())
    chinese = password_gate_response(_request("zh-CN,zh;q=0.9"), wrong_password=True)

    assert english.status_code == 403
    assert "Password Required" in bytes(english.body).decode()
    assert chinese.status_code == 403
    assert "密码错误，请重试。" in bytes(chinese.body).decode()
