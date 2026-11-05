"""Scoring limit of ContentPruningFilter: a page nested beyond it skips the scoring passes and nothing else."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup, Tag

from myrm_agent_harness.toolkits.web_fetch.processing import content_pruning
from myrm_agent_harness.toolkits.web_fetch.processing.content_pruning import ContentPruningFilter, _dom_path_units

_ARTICLE_SENTENCE = "The article body is long enough to be kept as the main content of the page. "
_PAGE = (
    "<html><body>"
    '<div class="sidebar"><a href="/1">first related link</a><a href="/2">second related link</a>'
    '<a href="/3">third related link</a><a href="/4">fourth related link</a></div>'
    "<nav>site navigation</nav>"
    f"<article><!-- inner comment --><p>{_ARTICLE_SENTENCE * 8}</p></article>"
    "<footer>copyright notice</footer>"
    "</body></html>"
)


def _body(html: str) -> Tag:
    soup = BeautifulSoup(html, "lxml")
    assert soup.body is not None
    return soup.body


class TestDomPathUnits:
    def test_sums_the_depth_of_every_element(self) -> None:
        body = _body("<body><div><p><b>x</b></p></div><i>y</i></body>")

        assert _dom_path_units(body, 1_000) == 1 + 2 + 3 + 1

    def test_ignores_text_and_comments(self) -> None:
        body = _body("<body>text<!-- note --><p>more</p></body>")

        assert _dom_path_units(body, 1_000) == 1

    def test_stops_counting_just_above_the_limit(self) -> None:
        body = _body("<body>" + "<div>" * 5_000 + "</div>" * 5_000 + "</body>")

        assert 100 < _dom_path_units(body, 100) <= 100 + 15


class TestScoringLimit:
    def test_page_within_the_limit_is_scored(self) -> None:
        blocks, _ = ContentPruningFilter().filter_content(_PAGE)

        joined = "".join(blocks)
        assert _ARTICLE_SENTENCE.strip() in joined
        assert "related link" not in joined

    def test_page_over_the_limit_skips_only_the_scoring(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(content_pruning, "_MAX_SCORING_PATH_UNITS", 0)

        blocks, _ = ContentPruningFilter().filter_content(_PAGE)

        joined = "".join(blocks)
        assert _ARTICLE_SENTENCE.strip() in joined
        assert "first related link" in joined
        assert "site navigation" not in joined
        assert "copyright notice" not in joined
        assert "inner comment" not in joined

    @pytest.mark.timeout(10)
    def test_nesting_bomb_keeps_its_content_without_being_scored(self) -> None:
        tail = f"<p>{_ARTICLE_SENTENCE * 8}</p>"
        bomb = (
            "<html><body>"
            + "<div>" * 400
            + "".join(f"<span>word{i} </span>" for i in range(8_000))
            + "</div>" * 400
            + tail
            + "</body></html>"
        )

        blocks, _ = ContentPruningFilter().filter_content(bomb)

        assert _ARTICLE_SENTENCE.strip() in "".join(blocks)
