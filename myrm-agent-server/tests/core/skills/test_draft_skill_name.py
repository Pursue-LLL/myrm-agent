"""The directory name an approved draft is written under."""

from __future__ import annotations

import re

import pytest

from app.core.skills.utils import slugify_draft_skill_name


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        pytest.param("report-builder", "report-builder", id="already-a-slug"),
        pytest.param("Report Builder", "Report-Builder", id="space-becomes-a-hyphen"),
        pytest.param("report   builder", "report-builder", id="a-run-becomes-one-hyphen"),
        pytest.param("report-builder.", "report-builder", id="trailing-full-stop-dropped"),
        pytest.param("  padded  ", "padded", id="padding-dropped"),
        pytest.param("-edge-", "edge", id="edge-hyphens-dropped"),
        pytest.param("évaluation rapide", "valuation-rapide", id="non-ascii-letter-replaced"),
        pytest.param("../skills/report-builder", "skills-report-builder", id="path-flattened"),
        pytest.param("report\0builder", "report-builder", id="nul-replaced"),
        pytest.param("skill-\u212a", "skill", id="kelvin-sign-is-not-k"),
        pytest.param("a" * 70, "a" * 64, id="cut-at-64-characters"),
        pytest.param("技能", "auto-skill", id="nothing-left"),
        pytest.param("", "auto-skill", id="empty"),
    ],
)
def test_a_draft_name_becomes_its_directory_name(name: str, slug: str) -> None:
    assert slugify_draft_skill_name(name) == slug


@pytest.mark.parametrize(
    "name", ["..", ".", "/", "../../etc", "/abs/path", "a/b", "a\0b", "line\nbreak", "\u212a", "~", "C:\\dir"]
)
def test_a_draft_name_never_becomes_more_than_one_directory_entry_name(name: str) -> None:
    """The lookup that judges where approval writes relies on this: no separator, no NUL, never empty."""
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", slugify_draft_skill_name(name))
