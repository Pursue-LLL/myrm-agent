"""The catalog names every model-visible skill that has no inline entry, and one resolver decides who earns an entry."""

from __future__ import annotations

import re

from myrm_agent_harness.agent.skills.runtime.catalog_display import (
    resolve_catalog_display_skills,
    should_mount_skill_search_tool,
)
from myrm_agent_harness.agent.skills.runtime.registry import (
    L1_HIDDEN_NAMES_MAX_TOKENS,
    get_metadata_summary,
)
from myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery import render_bound_skills_catalog
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.utils.text_utils import get_token_count

_LONG = "detailed capability description " * 20
_NAMES_LINE = re.compile(r"^ <hidden_skill_names>(.*)</hidden_skill_names>$", re.MULTILINE)


def _skill(name: str, *, description: str = _LONG, always: bool = False) -> SkillMetadata:
    return SkillMetadata(
        storage_skill_id=f"id-{name}",
        name=name,
        description=description,
        model_invocable=True,
        available=True,
        always=always,
    )


def _library(count: int, *, description: str = _LONG) -> list[SkillMetadata]:
    return [_skill(f"capability-{idx:03d}", description=description) for idx in range(count)]


def _peripheral(skills: list[SkillMetadata]) -> dict[str, dict[str, object]]:
    return {skill.id: {"is_core": False} for skill in skills}


def _names_line(xml: str) -> list[str]:
    match = _NAMES_LINE.search(xml)
    assert match is not None, xml
    return match.group(1).split(", ")


class TestHiddenNamesLine:
    def test_every_hidden_skill_is_named_and_no_inline_skill_is_repeated(self) -> None:
        skills = _library(40)
        rendered = render_bound_skills_catalog(skills)
        resolution = resolve_catalog_display_skills(skills)
        assert rendered is not None and resolution.display_skills

        assert _names_line(rendered.xml) == sorted(skill.name for skill in resolution.hidden_skills)
        assert not {skill.name for skill in resolution.display_skills} & set(_names_line(rendered.xml))

    def test_a_library_without_a_single_inline_entry_is_still_fully_named(self) -> None:
        skills = _library(57)
        rendered = render_bound_skills_catalog(skills, skill_configs=_peripheral(skills))

        assert rendered is not None
        assert "<skill " not in rendered.xml
        assert _names_line(rendered.xml) == sorted(skill.name for skill in skills)
        assert rendered.hidden_skill_count == 57
        assert "skill_search_tool" in rendered.xml

    def test_the_line_does_not_depend_on_the_order_skills_were_loaded_in(self) -> None:
        skills = _library(30)
        forward = render_bound_skills_catalog(skills, skill_configs=_peripheral(skills))
        backward = render_bound_skills_catalog(list(reversed(skills)), skill_configs=_peripheral(skills))

        assert forward is not None and backward is not None
        assert forward.hash == backward.hash

    def test_nothing_is_named_when_every_skill_fits_inline(self) -> None:
        xml = get_metadata_summary([_skill("alpha-skill", description="short")])

        assert "hidden_skill_names" not in xml
        assert "routing_rules" not in xml

    def test_a_130_skill_library_is_named_in_full_within_the_cap(self) -> None:
        names = [f"workflow-capability-{idx:03d}" for idx in range(130)]
        xml = get_metadata_summary([], hidden_skill_names=names)

        assert _names_line(xml) == names
        assert get_token_count(xml) < L1_HIDDEN_NAMES_MAX_TOKENS

    def test_a_library_beyond_the_cap_lists_an_alphabetical_prefix_and_counts_the_rest(self) -> None:
        names = [f"workflow-capability-{idx:04d}" for idx in range(600)]
        xml = get_metadata_summary([], hidden_skill_names=names)
        listed = _names_line(xml)

        overflow = listed.pop()
        assert re.fullmatch(r"and \d+ more not listed \(use skill_search_tool\)", overflow)
        assert listed == names[: len(listed)]
        assert len(listed) + int(overflow.split()[1]) == len(names)
        assert get_token_count(" <hidden_skill_names>" + ", ".join(listed) + ", ") <= L1_HIDDEN_NAMES_MAX_TOKENS + 8


class TestOneResolver:
    def test_an_empty_config_is_the_same_state_as_no_config(self) -> None:
        skills = _library(40)
        absent = resolve_catalog_display_skills(skills, skill_configs=None)
        empty = resolve_catalog_display_skills(skills, skill_configs={})

        assert [s.name for s in empty.display_skills] == [s.name for s in absent.display_skills]
        assert empty.hidden_skill_count == absent.hidden_skill_count > 0
        assert empty.overflow_count == absent.overflow_count
        rendered_absent = render_bound_skills_catalog(skills, skill_configs=None)
        rendered_empty = render_bound_skills_catalog(skills, skill_configs={})
        assert rendered_absent is not None and rendered_empty is not None
        assert rendered_absent.hash == rendered_empty.hash
        assert should_mount_skill_search_tool(skills, skill_configs={}) is should_mount_skill_search_tool(skills)

    def test_an_always_skill_keeps_its_first_claim_when_the_agent_has_a_config(self) -> None:
        mcp = _skill("zzz-mcp-github", always=True)
        ticked = _skill("alpha-skill")
        other = _skill("beta-skill")

        resolution = resolve_catalog_display_skills([other, ticked, mcp], skill_configs={ticked.id: {"is_core": True}})

        assert [s.name for s in resolution.display_skills] == ["zzz-mcp-github", "alpha-skill"]
        assert [s.name for s in resolution.hidden_skills] == ["beta-skill"]

    def test_an_explicit_peripheral_choice_beats_the_always_flag(self) -> None:
        pinned = _skill("pinned-skill", always=True)

        resolution = resolve_catalog_display_skills([pinned], skill_configs={pinned.id: {"is_core": False}})

        assert resolution.display_skills == []
        assert [s.name for s in resolution.hidden_skills] == ["pinned-skill"]

    def test_a_skill_missing_from_a_non_empty_config_is_not_core(self) -> None:
        ticked, unlisted = _skill("alpha-skill"), _skill("beta-skill")

        resolution = resolve_catalog_display_skills([ticked, unlisted], skill_configs={ticked.id: {"is_core": True}})

        assert [s.name for s in resolution.display_skills] == ["alpha-skill"]
        assert [s.name for s in resolution.hidden_skills] == ["beta-skill"]

    def test_core_skills_beyond_the_budget_are_named_and_counted_as_overflow(self) -> None:
        skills = _library(40)
        configs: dict[str, dict[str, object]] = {skill.id: {"is_core": True} for skill in skills[:30]}
        configs.update({skill.id: {"is_core": False} for skill in skills[30:]})

        resolution = resolve_catalog_display_skills(skills, skill_configs=configs)
        rendered = render_bound_skills_catalog(skills, skill_configs=configs)

        assert 0 < len(resolution.display_skills) < 30
        assert resolution.overflow_count == 30 - len(resolution.display_skills)
        assert rendered is not None
        assert {s.name for s in resolution.hidden_skills} == set(_names_line(rendered.xml))
        assert skills[29].name in _names_line(rendered.xml)

    def test_peripheral_skills_are_not_overflow(self) -> None:
        skills = _library(10)

        resolution = resolve_catalog_display_skills(skills, skill_configs=_peripheral(skills))

        assert resolution.overflow_count == 0
        assert resolution.hidden_skill_count == 10

    def test_runtime_counts_and_the_rendered_catalog_agree(self) -> None:
        skills = _library(40)
        configs: dict[str, dict[str, object]] = {skills[0].id: {"is_core": True}}

        resolution = resolve_catalog_display_skills(skills, skill_configs=configs)
        rendered = render_bound_skills_catalog(skills, skill_configs=configs)

        assert rendered is not None
        assert rendered.hidden_skill_count == resolution.hidden_skill_count == 39
        assert rendered.xml.count("<skill ") == len(resolution.display_skills) == 1
