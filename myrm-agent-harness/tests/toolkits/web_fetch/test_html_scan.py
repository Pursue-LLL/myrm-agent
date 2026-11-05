"""Linear-time HTML scans: the same results as the regexes they replace, and bounded cost on hostile pages."""

from __future__ import annotations

import random
import re

import pytest

from myrm_agent_harness.toolkits.web_fetch.processing.antibot_detector import is_blocked
from myrm_agent_harness.toolkits.web_fetch.processing.html_scan import (
    body_content,
    extract_title,
    strip_script_and_style,
    strip_tags,
)

# The regexes the scans replace. They define the expected result for every input.
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_BODY_RE = re.compile(r"<body\b[^>]*>([\s\S]*)</body>", re.IGNORECASE)
_SCRIPT_RE = re.compile(r"<script\b[\s\S]*?</script>", re.IGNORECASE)
_STYLE_RE = re.compile(r"<style\b[\s\S]*?</style>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")

_PAGE_SIZE = 750_000


class TestExtractTitle:
    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            ("<head><title>Hello</title></head>", "Hello"),
            ("<TITLE>Loud</TITLE>", "Loud"),
            ('<title lang="en">With attribute</title>', "With attribute"),
            ("<title>Two\nlines</title>", "Two\nlines"),
            ("<title></title>", ""),
            ("<title>first</title><title>second</title>", "first"),
            ("<p>no title here</p>", None),
            ("<title>never closed", None),
            ("<title never ended", None),
        ],
    )
    def test_examples(self, html: str, expected: str | None) -> None:
        assert extract_title(html) == expected


class TestBodyContent:
    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            ("<html><body>text</body></html>", "text"),
            ('<BODY class="page">text</BODY>', "text"),
            ("<body><script>'</body>'</script>tail</body>", "<script>'</body>'</script>tail"),
            ("<body></body>", ""),
            ("<body>never closed", None),
            ("no body at all</body>", None),
            ("<bodyguard>text</body>", None),
            ("<body never ended</body>", None),
        ],
    )
    def test_examples(self, html: str, expected: str | None) -> None:
        assert body_content(html) == expected


class TestStripScriptAndStyle:
    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            ("a<script>x=1</script>b<style>p{}</style>c", "abc"),
            ("a<SCRIPT type='x'>x=1</SCRIPT>b", "ab"),
            ("a<script>1</script>b<script>2</script>c", "abc"),
            ("a<script>never closed", "a<script>never closed"),
            ("a<scripts>kept</scripts>b", "a<scripts>kept</scripts>b"),
            ("a<style>p{}</style>b<script>x", "ab<script>x"),
        ],
    )
    def test_examples(self, html: str, expected: str) -> None:
        assert strip_script_and_style(html) == expected


class TestStripTags:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("<p>a</p><b>b</b>", "ab"),
            ('<a href="x\ny">link</a>', "link"),
            ("a<>b", "a<>b"),
            ("a < b", "a < b"),
            ("a<<b>c", "ac"),
            ("1 < 2 and 3 > 2", "1  2"),
        ],
    )
    def test_examples(self, text: str, expected: str) -> None:
        assert strip_tags(text) == expected


class TestEquivalenceWithTheRegexes:
    _TOKENS = (
        *("<title", "</title>", "<title>", "<TiTle ", "TITLE", "</TITLE>"),
        *("<body", "</body>", "<body>", "<bodyx"),
        *("<script", "</script>", "<SCRIPT ", "<scripts", "<style", "</style>", "<STYLE>", "</STYLE>"),
        *("<", ">", "<>", "<<", ">>", "</", "<p>", "a=b"),
        *("x", " ", "\n", "\r", "\t", "é", "İ", "ſ", "hello world "),
    )

    def test_random_markup_gives_the_same_results(self) -> None:
        rnd = random.Random(2026)
        for _ in range(20_000):
            html = "".join(rnd.choice(self._TOKENS) for _ in range(rnd.randint(0, 16)))
            title = _TITLE_RE.search(html)
            body = _BODY_RE.search(html)

            assert extract_title(html) == (title.group(1) if title else None), html
            assert body_content(html) == (body.group(1) if body else None), html
            assert strip_script_and_style(html) == _STYLE_RE.sub("", _SCRIPT_RE.sub("", html)), html
            assert strip_tags(html) == _TAG_RE.sub("", html), html


@pytest.mark.timeout(10)
class TestHostilePages:
    """Page-size inputs that make the replaced regexes rescan the whole page once per opener."""

    def test_title_openers_without_a_close(self) -> None:
        assert extract_title("<title" * (_PAGE_SIZE // 6)) is None

    def test_body_openers_without_a_tag_end(self) -> None:
        assert body_content("<body" * (_PAGE_SIZE // 5)) is None

    def test_script_openers_without_a_close_stay_in_the_page(self) -> None:
        page = "<script" * (_PAGE_SIZE // 7)

        assert strip_script_and_style(page) == page

    def test_script_openers_closed_only_at_the_very_end_are_one_block(self) -> None:
        assert strip_script_and_style("<script>" * (_PAGE_SIZE // 8) + "</script>tail") == "tail"

    def test_angle_brackets_without_a_tag_end(self) -> None:
        page = "<" * _PAGE_SIZE

        assert strip_tags(page) == page

    @pytest.mark.parametrize("opener", ["<script", "<style"])
    def test_anti_bot_check_survives_unclosed_blocks_on_a_large_page(self, opener: str) -> None:
        assert is_blocked(200, "<html>" + opener * (_PAGE_SIZE // len(opener))) == (False, "")

    def test_anti_bot_check_survives_unclosed_blocks_on_a_forbidden_page(self) -> None:
        blocked, reason = is_blocked(403, "<html>" + "<script" * (_PAGE_SIZE // 7))

        assert blocked
        assert reason.startswith("HTTP 403 with HTML content")
