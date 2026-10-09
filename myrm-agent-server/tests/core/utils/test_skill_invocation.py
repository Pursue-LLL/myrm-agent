"""Unit tests for app.core.utils.skill_invocation."""

from __future__ import annotations

from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag

from app.core.utils.skill_invocation import decorate_behind_skill_tag


def test_decorate_behind_skill_tag_only_touches_what_follows_the_tag() -> None:
    assert decorate_behind_skill_tag("[use a] hi", lambda text: f"<{text}>") == "[use a]\n\n<hi>"
    assert decorate_behind_skill_tag("hi", lambda text: f"<{text}>") == "<hi>"
    assert decorate_behind_skill_tag("see [use a] later", lambda text: f"<{text}>") == "<see [use a] later>"


def test_decorate_behind_skill_tag_lets_the_decoration_replace_the_text() -> None:
    out = decorate_behind_skill_tag("[use a,b]   do it", lambda _text: "REFERENCE")

    invocation = parse_use_tag(out)
    assert invocation is not None
    assert invocation.references == ("a", "b")
    assert invocation.text == "REFERENCE"


def test_decorate_behind_skill_tag_adds_no_blank_lines_after_a_bare_tag() -> None:
    assert decorate_behind_skill_tag("[use a]", lambda text: text) == "[use a]"
