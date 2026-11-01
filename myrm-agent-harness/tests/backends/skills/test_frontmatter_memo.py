"""Tests for the per-content memo in front of ``parse_skill_frontmatter``.

[INPUT]
- backends.skills._utils::parse_skill_frontmatter, _parse_frontmatter_fields (POS: the parser and the uncached parse it memoizes)

[OUTPUT]
- Fails when a memoized parse differs from a fresh one, when an edit of one returned frontmatter leaks into the next
  parse, when an invalid frontmatter is pinned instead of failing every time, or when a different skill name is
  answered from another name's entry.

[POS]
The frontmatter fields have their own files; this one pins what the memo may and may not change about the parse.
"""

from __future__ import annotations

import logging

import pytest

from myrm_agent_harness.backends.skills import _utils
from myrm_agent_harness.backends.skills._utils import SkillFrontmatter, SkillMetadataError, parse_skill_frontmatter

_RICH = """---
name: rich-skill
description: A skill declaring most of what the parser understands.
metadata:
  team: platform
requires:
  bins: [git]
  env: [RICH_SKILL_TOKEN]
requires-tools: [bash, read_file]
allowed-domains: [example.com]
required-oauth-issuers: [google_workspace]
contract:
  steps: [plan, act]
  key_judgments:
    - judgment_id: j1
      description: decide
      condition: when ready
      true_branch: go
      false_branch: wait
---

Body.
"""
_INVALID = "---\nname: broken\n---\n\nNo description, so the parser rejects it.\n"


@pytest.fixture
def parse_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Skill names of every parse that really ran (a memo hit never reaches ``_parse_frontmatter_fields``)."""
    calls: list[str] = []
    real = _utils._parse_frontmatter_fields

    def counting(content: str, skill_dir_name: str) -> SkillFrontmatter:
        calls.append(skill_dir_name)
        return real(content, skill_dir_name)

    monkeypatch.setattr(_utils, "_parse_frontmatter_fields", counting)
    return calls


def test_memoized_parse_equals_a_fresh_parse() -> None:
    fresh = _utils._parse_frontmatter_fields(_RICH, "rich-skill")

    assert parse_skill_frontmatter(_RICH, "rich-skill") == fresh
    assert parse_skill_frontmatter(_RICH, "rich-skill") == fresh


def test_identical_text_is_parsed_once(parse_calls: list[str]) -> None:
    parse_skill_frontmatter(_RICH, "rich-skill")
    parse_skill_frontmatter(_RICH, "rich-skill")

    assert parse_calls == ["rich-skill"]


def test_an_edited_text_is_parsed_again(parse_calls: list[str]) -> None:
    parse_skill_frontmatter(_RICH, "rich-skill")

    edited = parse_skill_frontmatter(_RICH.replace("A skill declaring", "An edited skill declaring"), "rich-skill")

    assert edited.description.startswith("An edited skill")
    assert len(parse_calls) == 2


def test_the_skill_name_is_part_of_the_key(parse_calls: list[str]) -> None:
    parse_skill_frontmatter(_RICH, "first-dir")
    parse_skill_frontmatter(_RICH, "second-dir")

    assert parse_calls == ["first-dir", "second-dir"]


def test_a_callers_edit_of_one_parse_never_reaches_the_next() -> None:
    expected = _utils._parse_frontmatter_fields(_RICH, "rich-skill")
    first = parse_skill_frontmatter(_RICH, "rich-skill")

    first.metadata["team"] = "tampered"
    first.metadata["injected"] = "yes"
    first.requires_tools.append("injected")
    assert first.requires is not None
    first.requires.bins.append("injected")
    first.requires.env.clear()
    assert first.allowed_domains is not None
    first.allowed_domains.clear()
    first.required_oauth_issuers.append("injected")

    assert parse_skill_frontmatter(_RICH, "rich-skill") == expected


def test_an_invalid_frontmatter_fails_every_time(parse_calls: list[str]) -> None:
    for _ in range(3):
        with pytest.raises(SkillMetadataError):
            parse_skill_frontmatter(_INVALID, "broken")

    assert len(parse_calls) == 3, "a rejected skill is never answered from the memo"


def test_a_repeated_parse_warns_once_per_text(caplog: pytest.LogCaptureFixture) -> None:
    content = _RICH.replace("name: rich-skill\n", "name: rich-skill\nunheard-of-field: 1\n")

    with caplog.at_level(logging.WARNING, logger=_utils.logger.name):
        for _ in range(3):
            parse_skill_frontmatter(content, "rich-skill")

    unknown_field_warnings = [r for r in caplog.records if "unknown frontmatter fields" in r.getMessage()]
    assert len(unknown_field_warnings) == 1
