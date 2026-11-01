"""The prebuilt skill library stays findable through the search tool's lexical path.

[INPUT]
- assets/prebuilt_skills/*/SKILL.md: the skills every install ships, parsed the way the skill loader parses them
- tests/support/skill_search_contract_cases.py: user intents, the query an agent writes for each, the skills that satisfy it
- myrm_agent_harness.agent.meta_tools.skills.search.engine::SkillSearchEngine (POS: the engine behind ``skill_search_tool``)

[OUTPUT]
- (tests only)

[POS]
The ruler of skill discovery over the real library. ``SkillSearchEngine`` matches words in a skill's name and description,
so the cases hold the query format the tool asks for (English keywords, alone or after user-language words) and the
user's own English sentence sent unchanged. A user-language sentence sent unchanged is not held: the library is English.
The harness golden benchmark runs on mock skills with no CJK text; this one runs on the library an agent really searches.
"""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import pytest
from myrm_agent_harness.agent.meta_tools.skills.search.engine import SkillSearchEngine
from myrm_agent_harness.backends.skills._utils import parse_skill_frontmatter
from myrm_agent_harness.backends.skills.types import SkillMetadata

from tests.support.skill_search_contract_cases import (
    AUTHORED_EN,
    AUTHORED_MIXED,
    BLIND_EN,
    BLIND_MIXED,
    SearchCase,
)

_PREBUILT_SKILLS = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills"

# ``discover_capability_tool`` hands the agent this many matches per search.
_RESULTS_RETURNED = 10

# Share of a group's intents that must reach a satisfying skill. Both leave room for the library to grow
# near-duplicates of a skill, yet sit close enough to the measured results that a broken tokenizer or scorer fails.
_KEYWORD_SHARE = 0.9  # queries written the way the tool asks: every case reached a skill when measured
_RAW_SHARE = 0.7  # the user's own English sentence sent unchanged as the query: 16 of 18 and 15 of 20 when measured


def _sent_unchanged(cases: tuple[SearchCase, ...]) -> tuple[SearchCase, ...]:
    return tuple(replace(case, query=case.intent) for case in cases)


_GROUPS: dict[str, tuple[tuple[SearchCase, ...], float]] = {
    "authored-en": (AUTHORED_EN, _KEYWORD_SHARE),
    "authored-mixed": (AUTHORED_MIXED, _KEYWORD_SHARE),
    "blind-en": (BLIND_EN, _KEYWORD_SHARE),
    "blind-mixed": (BLIND_MIXED, _KEYWORD_SHARE),
    "raw-english-authored": (_sent_unchanged(AUTHORED_EN), _RAW_SHARE),
    "raw-english-blind": (_sent_unchanged(BLIND_EN), _RAW_SHARE),
}


@pytest.fixture(scope="module")
def library() -> list[SkillMetadata]:
    skills: list[SkillMetadata] = []
    for skill_md in sorted(_PREBUILT_SKILLS.glob("*/SKILL.md")):
        directory = skill_md.parent.name
        frontmatter = parse_skill_frontmatter(skill_md.read_text(encoding="utf-8"), directory)
        skills.append(
            SkillMetadata(
                name=frontmatter.name or directory,
                description=frontmatter.description,
                storage_skill_id=directory,
            )
        )
    return skills


@pytest.fixture(scope="module")
def engine(library: list[SkillMetadata]) -> SkillSearchEngine:
    return SkillSearchEngine(library)


@pytest.mark.parametrize("group", _GROUPS)
def test_cases_name_skills_that_exist(group: str, library: list[SkillMetadata]) -> None:
    """A renamed or removed skill must fail here, not turn its case into a silent miss."""
    names = {skill.name for skill in library}
    cases, _ = _GROUPS[group]
    stale = {case.key: sorted(case.expected - names) for case in cases if not case.expected <= names}
    assert not stale, f"cases expect skills the library no longer ships: {stale}"


@pytest.mark.parametrize("group", _GROUPS)
def test_query_reaches_a_skill_that_satisfies_the_intent(group: str, engine: SkillSearchEngine) -> None:
    cases, share = _GROUPS[group]
    misses: list[str] = []
    for case in cases:
        returned = [match.name for match in engine.search_bm25(case.query, top_k=_RESULTS_RETURNED)]
        if case.expected.isdisjoint(returned):
            misses.append(f"{case.key}: {case.query!r} -> {returned[:3]}")
    required = math.ceil(share * len(cases))
    found = len(cases) - len(misses)
    assert found >= required, f"{group}: {found}/{len(cases)} intents found, {required} required; missed {misses}"
