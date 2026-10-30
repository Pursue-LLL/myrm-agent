"""The comparable body text of a raw file: only a leading frontmatter block is metadata, a horizontal rule is content."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.fingerprint import (
    compute_normalized_body_hash,
    compute_simhash,
    extract_body_text,
)

_FRONTMATTER = "---\ntitle: Notes\ntags: [a, b]\n---\n"
_SECTIONS = "Intro.\n\n---\n\nFirst chapter about apples.\n\n---\n\nOutro.\n"


@pytest.mark.parametrize("bom", ["", "\ufeff"], ids=["plain", "bom"])
def test_the_leading_frontmatter_block_is_not_part_of_the_body(bom: str) -> None:
    body = extract_body_text(f"{bom}{_FRONTMATTER}{_SECTIONS}")

    assert "title: Notes" not in body
    assert body == _SECTIONS


def test_text_between_two_horizontal_rules_stays_in_the_body() -> None:
    body = extract_body_text(_SECTIONS)

    assert body == _SECTIONS
    assert "apples" in extract_body_text(f"{_FRONTMATTER}{_SECTIONS}")


def test_documents_that_differ_between_two_horizontal_rules_fingerprint_differently() -> None:
    apples = _SECTIONS
    oranges = _SECTIONS.replace("apples", "oranges, which are another fruit entirely")

    assert compute_normalized_body_hash(apples) != compute_normalized_body_hash(oranges)
    assert compute_simhash(apples) != compute_simhash(oranges)


def test_a_document_without_frontmatter_is_compared_as_it_is() -> None:
    assert extract_body_text("# Title\n\nPlain body.") == "# Title\n\nPlain body."
