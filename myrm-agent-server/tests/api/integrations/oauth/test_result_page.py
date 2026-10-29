"""The page the OAuth provider sends the user back to: what it says, what it escapes, and that it stays readable."""

from __future__ import annotations

import html
import re

import pytest

from app.api.integrations.oauth.result_page import OAuthOutcome, oauth_result_response
from tests.support.wcag_contrast import Theme, assert_readable, assert_visible

_THEMES: tuple[Theme, ...] = ("light", "dark")


def _page(outcome: OAuthOutcome, detail: str | None = None) -> str:
    return bytes(oauth_result_response(outcome, detail=detail).body).decode()


def _visible_text(page: str) -> str:
    without_code = re.sub(r"<(style|script)>.*?</\1>", "", page, flags=re.DOTALL)
    return re.sub(r"<[^>]+>", " ", without_code)


@pytest.mark.parametrize(
    ("outcome", "status"),
    [
        (OAuthOutcome.SUCCESS, 200),
        (OAuthOutcome.DENIED, 400),
        (OAuthOutcome.EXPIRED, 400),
        (OAuthOutcome.FAILED, 400),
        (OAuthOutcome.UNREACHABLE, 500),
    ],
)
def test_each_outcome_has_its_status(outcome: OAuthOutcome, status: int) -> None:
    assert oauth_result_response(outcome).status_code == status


@pytest.mark.parametrize("outcome", list(OAuthOutcome))
def test_the_page_says_it_in_english_and_chinese(outcome: OAuthOutcome) -> None:
    page = _page(outcome)
    assert '<html lang="en">' in page
    chinese = re.findall(r'<span lang="zh-Hans">([^<]+)</span>', page)
    assert len(chinese) == 2
    assert all(re.search(r"[\u4e00-\u9fff]", text) for text in chinese)


@pytest.mark.parametrize("outcome", list(OAuthOutcome))
@pytest.mark.parametrize("mechanism", ["HTTP", "token", "OAuth", "exchange", "state", "exception", "traceback"])
def test_the_copy_names_no_mechanism(outcome: OAuthOutcome, mechanism: str) -> None:
    assert mechanism.lower() not in _visible_text(_page(outcome)).lower()


@pytest.mark.parametrize("outcome", list(OAuthOutcome))
def test_the_page_is_sized_for_a_phone_and_kept_out_of_search(outcome: OAuthOutcome) -> None:
    page = _page(outcome)
    assert '<meta name="viewport" content="width=device-width,initial-scale=1"/>' in page
    assert '<meta name="robots" content="noindex, nofollow"/>' in page


def test_the_providers_words_are_shown_as_text() -> None:
    payload = '<img src=x onerror="alert(1)"> & more'
    page = _page(OAuthOutcome.DENIED, detail=payload)
    assert payload not in page
    assert f'<p class="detail">{html.escape(payload)}</p>' in page


@pytest.mark.parametrize("detail", [None, ""])
def test_no_explanation_is_drawn_without_providers_words(detail: str | None) -> None:
    assert 'class="detail"' not in _page(OAuthOutcome.DENIED, detail=detail)


@pytest.mark.parametrize("outcome", list(OAuthOutcome))
def test_only_a_completed_authorization_closes_the_tab(outcome: OAuthOutcome) -> None:
    assert ("window.close" in _page(outcome)) is (outcome is OAuthOutcome.SUCCESS)


@pytest.mark.parametrize("outcome", list(OAuthOutcome))
def test_no_colour_is_set_outside_the_stylesheet(outcome: OAuthOutcome) -> None:
    markup = _page(outcome).split("</style>")[1]
    assert not re.search(r"\bstyle\s*=|\.style\.", markup)


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize(
    ("text", "surface"),
    [("body", ".card"), ("p", ".card")],
    ids=["title", "instruction"],
)
def test_text_is_readable_on_its_surface(theme: Theme, text: str, surface: str) -> None:
    assert_readable(_page(OAuthOutcome.SUCCESS), theme, text, surface)


@pytest.mark.parametrize("theme", _THEMES)
@pytest.mark.parametrize("tone", [".ok", ".warn", ".bad"])
def test_the_status_icon_stands_out_from_the_card(theme: Theme, tone: str) -> None:
    assert_visible(_page(OAuthOutcome.SUCCESS), theme, tone, ("color",), ".card")


def test_every_icon_tone_a_page_uses_is_one_the_contrast_checks_read() -> None:
    tones = {m for outcome in OAuthOutcome for m in re.findall(r'<svg class="icon (\w+)"', _page(outcome))}
    assert tones == {"ok", "warn", "bad"}
