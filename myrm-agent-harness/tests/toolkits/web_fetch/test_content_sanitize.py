"""Tests for web fetch markdown sanitization."""

from __future__ import annotations

import random
import re
import time

import pytest

from myrm_agent_harness.toolkits.web_fetch.processing.content_sanitize import (
    strip_base64_images_from_markdown,
)

_BLOB = "iVBORw0KGgo" + "A" * 200


def test_strip_base64_markdown_image() -> None:
    blob = "A" * 200
    md = f"![chart](data:image/png;base64,{blob})"
    out = strip_base64_images_from_markdown(md)
    assert "[IMAGE: chart]" in out
    assert "base64" not in out


class TestPlaceholders:
    def test_markdown_image_without_alt(self) -> None:
        assert strip_base64_images_from_markdown(f"![](data:image/png;base64,{_BLOB})") == "[IMAGE]"

    def test_alt_text_is_trimmed(self) -> None:
        out = strip_base64_images_from_markdown(f"![  a chart  ](data:image/png;base64,{_BLOB})")
        assert out == "[IMAGE: a chart]"

    def test_whitespace_between_parenthesis_and_uri(self) -> None:
        out = strip_base64_images_from_markdown(f"![x]( \n data:image/webp;base64,{_BLOB} )")
        assert out == "[IMAGE: x]"

    def test_parenthesised_target_without_image_syntax(self) -> None:
        out = strip_base64_images_from_markdown(f"see (data:image/gif;base64,{_BLOB}) here")
        assert out == "see [IMAGE] here"

    def test_html_attribute_and_bare_uri(self) -> None:
        html = f'<img src="data:image/svg+xml;base64,{_BLOB}" alt="x"> and data:image/jpeg;base64,{_BLOB}.'
        out = strip_base64_images_from_markdown(html)
        assert out == '<img src="[IMAGE]" alt="x"> and [IMAGE].'

    def test_payload_wrapped_across_lines_inside_markdown_image(self) -> None:
        wrapped = "\n".join(_BLOB[i : i + 60] for i in range(0, len(_BLOB), 60))
        out = strip_base64_images_from_markdown(f"![wrapped](data:image/png;base64,{wrapped})")
        assert out == "[IMAGE: wrapped]"

    def test_surrounding_text_and_several_images_are_preserved(self) -> None:
        md = f"intro ![a](data:image/png;base64,{_BLOB}) middle ![b](data:image/png;base64,{_BLOB}) outro"
        assert strip_base64_images_from_markdown(md) == "intro [IMAGE: a] middle [IMAGE: b] outro"

    def test_text_without_data_uri_is_returned_unchanged(self) -> None:
        text = "# Title\n\nPlain ![logo](https://example.com/logo.png) and (parenthesised) [link](x)."
        assert strip_base64_images_from_markdown(text) is text

    @pytest.mark.parametrize(
        "text",
        [
            "data:image/png;utf8,not-base64",
            "data:text/plain;base64,SGVsbG8=",
            "data:image/;base64,AAAA",
            "data:image/png;base64,",
            "data:image/png base64 AAAA",
        ],
    )
    def test_other_uris_are_left_alone(self, text: str) -> None:
        assert strip_base64_images_from_markdown(text) == text

    def test_overlong_alt_text_stays_but_the_blob_is_replaced(self) -> None:
        alt = "caption " * 200
        out = strip_base64_images_from_markdown(f"![{alt}](data:image/png;base64,{_BLOB})")
        assert out == f"![{alt}][IMAGE]"


# The three patterns the scanner implements, applied as three passes — the behavioural reference for ordinary input.
_REFERENCE_MD = re.compile(r"!\[(?P<alt>[^\]]*)\]\(\s*data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+\)")
_REFERENCE_PAREN = re.compile(r"\(\s*data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+\)")
_REFERENCE_BARE = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+")


def _reference_strip(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        alt = (match.group("alt") or "").strip()
        return f"[IMAGE: {alt}]" if alt else "[IMAGE]"

    return _REFERENCE_BARE.sub("[IMAGE]", _REFERENCE_PAREN.sub("[IMAGE]", _REFERENCE_MD.sub(repl, text)))


_MIMES = ("png", "jpeg", "svg+xml", "webp", "gif", "x-icon", "avif")
_PAYLOADS = ("AAAA", "iVBORw0KGgo=", "AA AA\nBB", "A" * 50, "AA==", "\n\tAB CD\n")
_ALTS = ("", "chart", "  spaced alt  ", "a [nested b", "a)b", "long " * 30, "x ![y")
_FILLERS = ("text ", "\n", " ", "(", ")", "[", "]", "](", '<img src="', '">', "## h\n", "x", "e.g. ", "( ", " )")


def _random_document(rng: random.Random) -> str:
    def blob() -> str:
        return f"data:image/{rng.choice(_MIMES)};base64,{rng.choice(_PAYLOADS)}"

    def pad() -> str:
        return rng.choice(("", " ", "\n"))

    def element() -> str:
        roll = rng.random()
        if roll < 0.25:
            return f"![{rng.choice(_ALTS)}]({pad()}{blob()}{pad()})"
        if roll < 0.40:
            return f"({pad()}{blob()}{pad()})"
        if roll < 0.55:
            return f'<img src="{blob()}" alt="x">'
        if roll < 0.65:
            return blob()
        if roll < 0.70:
            return f"[{rng.choice(_ALTS)}]({blob()}"
        return rng.choice(_FILLERS)

    return "".join(element() for _ in range(rng.randint(1, 8)))


def test_matches_reference_patterns_on_ordinary_documents() -> None:
    rng = random.Random(20261104)
    for _ in range(3_000):
        document = _random_document(rng)
        assert strip_base64_images_from_markdown(document) == _reference_strip(document), repr(document)


class TestHostileInputs:
    """Inputs shaped like the worst case of the pattern-based approach; they sit at the 750 KB response cap."""

    _SIZE = 750_000
    # Linear scanning finishes these in tens of milliseconds; the bound only has to separate that from quadratic growth.
    _BUDGET_SECONDS = 2.0

    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("data:image/" * (_SIZE // 11), id="uri-marker-run-without-semicolon"),
            pytest.param("![" * (_SIZE // 2), id="image-openers-without-closer"),
            pytest.param("![a" + "](" * (_SIZE // 2), id="alt-closers-without-uri"),
            pytest.param("(" + " " * _SIZE + "data:image/png;base64,AAAA", id="whitespace-before-uri"),
            pytest.param("data:image/png;base64, " * (_SIZE // 23), id="empty-payloads"),
            pytest.param("![x](data:image/png;base64," + "A" * _SIZE + ")", id="single-huge-payload"),
        ],
    )
    def test_finishes_within_budget(self, text: str) -> None:
        started = time.perf_counter()
        out = strip_base64_images_from_markdown(text)
        assert time.perf_counter() - started < self._BUDGET_SECONDS
        assert len(out) <= len(text)

    def test_huge_payload_collapses_to_a_placeholder(self) -> None:
        out = strip_base64_images_from_markdown("![x](data:image/png;base64," + "A" * self._SIZE + ")")
        assert out == "[IMAGE: x]"
