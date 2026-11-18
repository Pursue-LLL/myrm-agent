"""`[use <reference>]` finds the skill a user means, whatever name the backend lists it under.

The tag only counts at the very start of the text and carries one or more comma-separated references, at most
``MAX_REFERENCE_LIST_CHARS`` characters of them: a longer list is ordinary text, so a tag stays small and the grammar
scans a run of whitespace in linear time.
The slash palette sends the catalog name (``audit-probe``). A product backend may list the same skill
under a runtime name (``audit_probe_skill``) with a storage id that is neither (``local::...``); the SOP
preload and the skill hooks must still reach it, and must never guess between two skills.
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator, Iterator
from unittest.mock import AsyncMock

import pytest
from langgraph.types import Command

from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.hooks import get_hook_executor, set_hook_executor
from myrm_agent_harness.agent.hooks.types import CommandHookDefinition, HookEvent
from myrm_agent_harness.agent.skill_agent import SkillAgent, wait_all_background_tasks
from myrm_agent_harness.agent.skill_agent.skill_reference import (
    MAX_REFERENCE_LIST_CHARS,
    parse_use_tag,
    resolve_skill_reference,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.utils.chat_utils import ChatHistoryReq


class TestUseTagGrammar:
    """Tests for parse_use_tag, the grammar of the leading [use skill_name] tag."""

    def test_basic_match(self) -> None:
        tag = parse_use_tag("[use daily_report_skill] generate today's report")
        assert tag is not None
        assert tag.references == ("daily_report_skill",)
        assert tag.text == "generate today's report"

    def test_literal_tag_is_kept_for_hosts_that_decorate_the_text(self) -> None:
        tag = parse_use_tag("[use a, b]   do it")
        assert tag is not None
        assert tag.tag == "[use a, b]"
        assert tag.text == "do it"

    def test_no_args(self) -> None:
        tag = parse_use_tag("[use deploy_skill]")
        assert tag is not None
        assert tag.references == ("deploy_skill",)
        assert tag.text == ""

    def test_with_args_trailing_space(self) -> None:
        tag = parse_use_tag("[use deploy_skill] staging  ")
        assert tag is not None
        assert tag.references == ("deploy_skill",)
        assert tag.text == "staging"

    def test_hyphenated_skill_name(self) -> None:
        tag = parse_use_tag("[use my-great-skill] do something")
        assert tag is not None
        assert tag.references == ("my-great-skill",)

    def test_no_match_plain_text(self) -> None:
        assert parse_use_tag("Just a normal message") is None

    def test_no_match_middle_of_text(self) -> None:
        assert parse_use_tag("Please [use test_skill] now") is None

    def test_no_match_behind_a_prefix_the_host_added(self) -> None:
        assert parse_use_tag("[Inbound channel message] channel=x\n---\n\n[use test_skill] now") is None

    def test_multiline_args(self) -> None:
        tag = parse_use_tag("[use test_skill] line1\nline2\nline3")
        assert tag is not None
        assert tag.text == "line1\nline2\nline3"

    def test_empty_skill_name_no_match(self) -> None:
        assert parse_use_tag("[use ] something") is None
        assert parse_use_tag("[use ,] something") is None

    def test_multi_skill_comma_separated(self) -> None:
        tag = parse_use_tag("[use skill_a,skill_b,skill_c] do it")
        assert tag is not None
        assert tag.references == ("skill_a", "skill_b", "skill_c")
        assert tag.text == "do it"

    def test_multi_skill_with_spaces(self) -> None:
        tag = parse_use_tag("[use skill_a, skill_b] args")
        assert tag is not None
        assert tag.references == ("skill_a", "skill_b")

    def test_multi_skill_no_args(self) -> None:
        tag = parse_use_tag("[use a,b]")
        assert tag is not None
        assert tag.references == ("a", "b")
        assert tag.text == ""

    def test_trailing_comma(self) -> None:
        tag = parse_use_tag("[use a,b,] args")
        assert tag is not None
        assert tag.references == ("a", "b")

    def test_any_whitespace_may_stand_between_the_keyword_and_the_first_name(self) -> None:
        tag = parse_use_tag("[use \n\t  a ,b ] go")
        assert tag is not None
        assert tag.references == ("a", "b")
        assert tag.tag == "[use \n\t  a ,b ]"

    def test_the_keyword_is_lower_case(self) -> None:
        assert parse_use_tag("[USE a] go") is None

    def test_whitespace_must_follow_the_keyword(self) -> None:
        assert parse_use_tag("[user] hello") is None

    def test_non_ascii_names_are_references(self) -> None:
        tag = parse_use_tag("[use 日报,周报] go")
        assert tag is not None
        assert tag.references == ("日报", "周报")

    @pytest.mark.parametrize(
        ("reference_list", "is_tag"),
        [
            ("a" * MAX_REFERENCE_LIST_CHARS, True),
            ("a" * (MAX_REFERENCE_LIST_CHARS + 1), False),
            (",".join(f"skill-{index}" for index in range(600)), False),
        ],
        ids=["at-the-limit", "one-past-the-limit", "hundreds-of-names"],
    )
    def test_a_reference_list_longer_than_the_limit_is_ordinary_text(self, reference_list: str, is_tag: bool) -> None:
        assert (parse_use_tag(f"[use {reference_list}] go") is not None) is is_tag

    @pytest.mark.parametrize(
        "text",
        ["[use" + " " * 100_000, "[use" + " " * 100_000 + "a", "[use" + " \n\t" * 33_334],
        ids=["spaces", "spaces-then-a-name", "mixed-whitespace"],
    )
    def test_a_long_run_of_whitespace_after_the_keyword_is_rejected_in_linear_time(self, text: str) -> None:
        """Overlapping whitespace quantifiers cost seconds here, and bounding the list alone does not cure it."""
        # CPU time, not wall-clock: a busy machine stretches the latter without the parser doing more work.
        started = time.process_time()
        assert parse_use_tag(text) is None
        assert time.process_time() - started < 0.25


def _meta(name: str, storage_skill_id: str | None = None) -> SkillMetadata:
    return SkillMetadata(name=name, description=f"{name} skill", storage_skill_id=storage_skill_id)


class TestResolveSkillReference:
    def test_exact_name_wins_over_a_canonical_twin(self) -> None:
        skills = [_meta("pdf_generator_skill"), _meta("pdf-generator")]

        assert resolve_skill_reference("pdf-generator", skills) is skills[1]

    def test_storage_id_resolves(self) -> None:
        skills = [_meta("audit_probe_skill", "local::0123456789abcdef")]

        assert resolve_skill_reference("local::0123456789abcdef", skills) is skills[0]

    @pytest.mark.parametrize(
        "reference",
        ["audit-probe", "Audit-Probe", "audit_probe", "audit_probe_skill", " audit-probe ", "audit probe"],
    )
    def test_spelling_variants_of_one_skill_resolve(self, reference: str) -> None:
        skills = [_meta("audit_probe_skill"), _meta("other_skill")]

        assert resolve_skill_reference(reference, skills) is skills[0]

    def test_ambiguous_spelling_resolves_to_nothing(self) -> None:
        skills = [_meta("foo-bar"), _meta("foo_bar_skill")]

        assert resolve_skill_reference("foo_bar", skills) is None

    @pytest.mark.parametrize("reference", ["", "   ", "missing", "audit"])
    def test_unknown_or_empty_reference_resolves_to_nothing(self, reference: str) -> None:
        assert resolve_skill_reference(reference, [_meta("audit_probe_skill")]) is None


_AUDIT_SKILL_MD = (
    "---\nname: audit-probe\ndescription: audit probe skill\n"
    "hooks:\n  PreToolUse:\n    - script: 'echo audited'\n      tools: [bash_*]\n---\n# audit-probe\n\nDo the thing.\n"
)
_STORAGE_ID = "local::0123456789abcdef"


class _ServerShapedBackend:
    """Lists skills under a runtime name and serves SKILL.md by that name or by storage id."""

    def __init__(self, listed: list[SkillMetadata], content_by_key: dict[str, str]) -> None:
        self._listed = listed
        self._content_by_key = content_by_key

    async def list_skills(self) -> list[SkillMetadata]:
        return list(self._listed)

    async def load_skills(self, skill_ids: list[str]) -> list[SkillMetadata]:
        return [s for s in self._listed if s.name in skill_ids or s.storage_skill_id in skill_ids]

    async def get_skill_content(self, skill_name: str) -> str:
        try:
            return self._content_by_key[skill_name]
        except KeyError:
            raise FileNotFoundError(skill_name) from None

    async def get_skill_resources(self, skill_name: str, path: str) -> bytes:
        raise FileNotFoundError(path)

    async def list_skill_resources(self, skill_name: str) -> list[str]:
        return []


def _agent(*listed: SkillMetadata) -> SkillAgent:
    content = {key: _AUDIT_SKILL_MD for skill in listed for key in (skill.name, skill.storage_skill_id) if key}
    return SkillAgent(llm=AsyncMock(), skill_backend=_ServerShapedBackend(list(listed), content))


@pytest.fixture(autouse=True)
def fresh_hook_session() -> Iterator[None]:
    previous = get_hook_executor()
    set_hook_executor(None)
    yield
    set_hook_executor(previous)


@pytest.fixture
def streamed_hooks(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    async def fake_run(self: BaseAgent, query: object, **_: object) -> AsyncGenerator[dict[str, object]]:
        executor = get_hook_executor()
        assert executor is not None
        seen.append(
            [h.command for h in executor.registry.get(HookEvent.PRE_TOOL_USE) if isinstance(h, CommandHookDefinition)]
        )
        yield {"type": "message", "data": "done"}

    monkeypatch.setattr(BaseAgent, "run", fake_run)
    return seen


@pytest.mark.asyncio
async def test_catalog_name_activates_the_hooks_of_a_runtime_named_skill(streamed_hooks: list[list[str]]) -> None:
    agent = _agent(_meta("audit_probe_skill", _STORAGE_ID))

    _ = [event async for event in agent.run("[use audit-probe] audit my shell")]
    await wait_all_background_tasks()

    assert streamed_hooks == [["echo audited"]]


@pytest.mark.asyncio
async def test_hitl_resume_finds_the_runtime_named_skill_of_the_interrupted_turn(
    streamed_hooks: list[list[str]],
) -> None:
    agent = _agent(_meta("audit_probe_skill", _STORAGE_ID))
    history: ChatHistoryReq = [["human", "[use audit-probe] audit my shell"], ["assistant", "let me run it"]]

    _ = [event async for event in agent.run(Command(resume={"decision": "approve"}), chat_history=history)]
    await wait_all_background_tasks()

    assert streamed_hooks == [["echo audited"]]


@pytest.mark.asyncio
async def test_two_references_to_one_skill_inject_it_once(streamed_hooks: list[list[str]]) -> None:
    agent = _agent(_meta("audit_probe_skill", _STORAGE_ID))

    query, _, preloaded = await agent._preload_explicit_skill("[use audit-probe,audit_probe_skill] go")

    assert [skill.name for skill in preloaded] == ["audit_probe_skill"]
    assert query.count("--- Skill: audit_probe_skill ---") == 1


@pytest.mark.asyncio
async def test_a_reference_list_past_the_limit_invokes_nothing() -> None:
    agent = _agent(_meta("audit_probe_skill", _STORAGE_ID))
    text = "[use audit-probe," + "x," * MAX_REFERENCE_LIST_CHARS + "] go"

    assert await agent._preload_explicit_skill(text) == (text, None, [])


@pytest.mark.asyncio
async def test_ambiguous_reference_activates_nothing(streamed_hooks: list[list[str]]) -> None:
    agent = _agent(_meta("foo-bar", "id-1"), _meta("foo_bar_skill", "id-2"))

    _ = [event async for event in agent.run("[use foo_bar] audit")]
    await wait_all_background_tasks()

    assert streamed_hooks == [[]]
