"""A PTC-routed MCP entry lists its functions in the catalog, within a budget of its own, and says how to call them."""

from __future__ import annotations

import re

import pytest

from myrm_agent_harness.agent.meta_tools.skills.select.skill_select_tool import build_skill_select_static_description
from myrm_agent_harness.agent.skills.runtime.catalog_display import resolve_catalog_display_skills
from myrm_agent_harness.agent.skills.runtime.function_index import (
    FUNCTION_INDEX_RULES,
    L1_FUNCTION_INDEX_MAX_TOKENS,
    fit_function_indexes,
)
from myrm_agent_harness.agent.skills.runtime.ptc_calling import CALL_SYNTAX, CALL_WORKFLOW
from myrm_agent_harness.agent.skills.runtime.registry import estimate_skill_entry_tokens, get_metadata_summary
from myrm_agent_harness.agent.skills.runtime.skill_catalog_delivery import render_bound_skills_catalog
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.utils.text_utils import get_token_count

_PLAIN_DESCRIPTION = "detailed capability description " * 20


def _mcp_skill(
    name: str,
    functions: list[str],
    *,
    available: bool = True,
    description: str = "Cluster operations",
) -> SkillMetadata:
    return SkillMetadata(
        name=name,
        description=description,
        available=available,
        always=True,
        mcp=MCPSkillData(server=name, tools=functions, config=[], inline_functions=functions),
    )


def _storage_skill(name: str) -> SkillMetadata:
    return SkillMetadata(
        storage_skill_id=f"id-{name}", name=name, description=_PLAIN_DESCRIPTION, model_invocable=True, available=True
    )


def _functions(prefix: str, count: int) -> list[str]:
    return [f"{prefix}_function_{idx:03d}" for idx in range(count)]


def _entry(xml: str, name: str) -> str:
    match = re.search(rf'<skill name="{name}".*?</skill>', xml, re.DOTALL)
    assert match is not None, xml
    return match.group(0)


class TestListedFunctions:
    def test_an_entry_lists_its_functions_and_the_rules_come_once_before_the_entries(self) -> None:
        xml = get_metadata_summary(
            [_mcp_skill("mcp_alpha_skill", ["list_pods", "get_pod"]), _mcp_skill("mcp_beta_skill", ["run_query"])]
        )

        alpha = _entry(xml, "mcp_alpha_skill")

        assert xml.count("<function_index_rules>") == 1
        assert xml.index("</function_index_rules>") < xml.index("<skill name=")
        assert " <functions>list_pods, get_pod</functions>" in alpha
        assert alpha.index("<description>") < alpha.index("<functions>")
        assert " <functions>run_query</functions>" in _entry(xml, "mcp_beta_skill")

    def test_a_skill_that_lists_nothing_renders_exactly_as_it_did_without_the_index(self) -> None:
        skill = _mcp_skill("mcp_alpha_skill", [])

        assert get_metadata_summary([skill]) == (
            "<skills>\n"
            ' <skill name="mcp_alpha_skill" available="true" trust="trusted" always="true">\n'
            " <description>Cluster operations</description>\n"
            " </skill>\n"
            "</skills>"
        )

    def test_only_available_mcp_skills_list_functions(self) -> None:
        skills = [
            _mcp_skill("mcp_down_skill", ["list_pods"], available=False),
            _storage_skill("plain-skill"),
            _mcp_skill("mcp_up_skill", ["list_nodes"]),
        ]

        fitted = fit_function_indexes(skills)

        assert list(fitted) == ["mcp_up_skill"]

    def test_the_rules_are_absent_when_no_entry_lists_functions(self) -> None:
        xml = get_metadata_summary([_storage_skill("plain-skill"), _mcp_skill("mcp_alpha_skill", [])])

        assert "function_index_rules" not in xml
        assert "<functions>" not in xml


class TestBudget:
    def test_an_index_never_changes_which_skills_earn_an_entry(self) -> None:
        library = [_storage_skill(f"skill-{idx:02d}") for idx in range(30)]
        listing = _mcp_skill("mcp_alpha_skill", _functions("pod", 150))
        silent = _mcp_skill("mcp_alpha_skill", _functions("pod", 150))
        silent.mcp.inline_functions = []

        listed = resolve_catalog_display_skills([listing, *library])
        unlisted = resolve_catalog_display_skills([silent, *library])

        assert [skill.name for skill in listed.display_skills] == [skill.name for skill in unlisted.display_skills]
        assert listed.overflow_count == unlisted.overflow_count
        assert estimate_skill_entry_tokens(listing) == estimate_skill_entry_tokens(silent)

    def test_an_index_is_listed_whole_or_not_at_all(self) -> None:
        oversized = _mcp_skill("mcp_big_skill", _functions("big", 600))
        assert get_token_count(f" <functions>{', '.join(oversized.mcp.inline_functions)}</functions>") > (
            L1_FUNCTION_INDEX_MAX_TOKENS
        )

        xml = get_metadata_summary([oversized])

        assert 'name="mcp_big_skill"' in xml
        assert "<functions>" not in xml
        assert "function_index_rules" not in xml

    def test_a_later_shorter_list_still_fits_after_one_that_does_not(self) -> None:
        skills = [_mcp_skill("mcp_big_skill", _functions("big", 600)), _mcp_skill("mcp_small_skill", ["ping"])]

        assert list(fit_function_indexes(skills)) == ["mcp_small_skill"]

    def test_all_lines_together_stay_within_the_ceiling(self) -> None:
        skills = [_mcp_skill(f"mcp_server_{idx}_skill", _functions(f"s{idx}", 60)) for idx in range(8)]
        one_line_cost = get_token_count(next(iter(fit_function_indexes(skills[:1]).values())))

        fitted = fit_function_indexes(skills)

        assert 0 < len(fitted) < len(skills)
        assert len(fitted) == L1_FUNCTION_INDEX_MAX_TOKENS // one_line_cost
        assert list(fitted) == [skill.name for skill in skills[: len(fitted)]]
        assert sum(get_token_count(line) for line in fitted.values()) <= L1_FUNCTION_INDEX_MAX_TOKENS


class TestRules:
    def test_the_rules_carry_the_calling_convention_the_skill_document_carries(self) -> None:
        rules = "\n".join(FUNCTION_INDEX_RULES)

        for line in CALL_SYNTAX.format(skill_name="<name>").splitlines():
            assert line in rules
        for line in CALL_WORKFLOW.splitlines():
            assert line in rules

    def test_the_rules_state_the_override_and_the_way_back_to_the_skill(self) -> None:
        rules = "\n".join(FUNCTION_INDEX_RULES)

        assert "can be used without selecting it" in rules
        assert "skip skill_select_tool" in rules
        assert "select the skill instead when you need every signature at once" in rules
        assert "/mcp/<name>/<function_name>.md" in rules

    @pytest.mark.parametrize(
        ("locale", "exception"),
        [(None, "can be used without selecting it"), ("zh-CN", "无需选择即可使用")],
    )
    def test_the_select_tool_leaves_room_for_the_catalog_exception(self, locale: str | None, exception: str) -> None:
        description = build_skill_select_static_description(locale)

        assert exception in description
        assert "MANDATORY" in description or "强制要求" in description
        assert "<functions>" not in description


class TestDelivery:
    def test_the_catalog_is_byte_stable_and_its_hash_follows_the_function_list(self) -> None:
        first = render_bound_skills_catalog([_mcp_skill("mcp_alpha_skill", ["list_pods", "get_pod"])])
        again = render_bound_skills_catalog([_mcp_skill("mcp_alpha_skill", ["list_pods", "get_pod"])])
        changed = render_bound_skills_catalog([_mcp_skill("mcp_alpha_skill", ["list_pods", "get_pod", "top_pods"])])

        assert first is not None and again is not None and changed is not None
        assert first.xml == again.xml
        assert first.hash == again.hash
        assert changed.hash != first.hash
