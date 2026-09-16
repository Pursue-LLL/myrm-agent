"""Tests for Agent responsibility-unit governance (read-only scan + merge plan)."""

from myrm_agent_harness.backends.profiles.types import AgentProfile
from pydantic import ValidationError

from app.api.agents._agent_response import _to_agent_response
from app.api.agents.governance import _merge_plan, _overlap_pairs, _profile_asset
from app.database.dto import AgentUpdate


def _asset(
    aid: str,
    skills: list[str] | None = None,
    tools: list[str] | None = None,
    subagents: list[str] | None = None,
) -> dict:
    return {
        "id": aid,
        "name": aid,
        "built_in": False,
        "agent_type": "individual",
        "skill_ids": skills or [],
        "tools": tools or [],
        "subagent_ids": subagents or [],
        "responsibility_scope": None,
        "owner_label": None,
        "acceptance_criteria": [],
    }


def test_profile_asset_reads_governance_metadata() -> None:
    profile = AgentProfile(
        id="a1",
        display_name="A1",
        metadata={
            "responsibility_scope": "Owns email replies",
            "owner_label": "Ming",
            "acceptance_criteria": ["Reply within a day"],
        },
    )
    asset = _profile_asset(profile)
    assert asset["responsibility_scope"] == "Owns email replies"
    assert asset["owner_label"] == "Ming"
    assert asset["acceptance_criteria"] == ["Reply within a day"]


def test_profile_asset_tolerates_missing_metadata() -> None:
    asset = _profile_asset(AgentProfile(id="a1", display_name="A1", metadata=None))
    assert asset["responsibility_scope"] is None
    assert asset["acceptance_criteria"] == []


def test_response_serializes_governance_fields() -> None:
    profile = AgentProfile(
        id="a1",
        display_name="A1",
        metadata={"responsibility_scope": "Scope", "owner_label": "Owner", "acceptance_criteria": ["Done"]},
    )
    response = _to_agent_response(profile)
    assert response.responsibility_scope == "Scope"
    assert response.owner_label == "Owner"
    assert response.acceptance_criteria == ["Done"]


def test_response_defaults_governance_fields() -> None:
    response = _to_agent_response(AgentProfile(id="a1", display_name="A1", metadata=None))
    assert response.responsibility_scope is None
    assert response.acceptance_criteria is None


def test_overlap_detects_shared_skills() -> None:
    pairs = _overlap_pairs([_asset("a", skills=["s1", "s2"]), _asset("b", skills=["s1", "s2", "s3"])])
    assert len(pairs) == 1
    assert pairs[0]["shared_skills"] == ["s1", "s2"]


def test_overlap_ignores_single_shared_skill_without_tools() -> None:
    pairs = _overlap_pairs([_asset("a", skills=["s1"]), _asset("b", skills=["s1"])])
    assert pairs == []


def test_merge_plan_moves_only_source_unique_items() -> None:
    plan = _merge_plan(
        _asset("src", skills=["s1", "s2"], subagents=["m1"]),
        _asset("tgt", skills=["s2"], subagents=["m1", "m2"]),
    )
    assert plan["move_skills"] == ["s1"]
    assert plan["move_subagents"] == []


def test_merge_plan_flags_dual_responsibility() -> None:
    source = _asset("src")
    source["responsibility_scope"] = "Emails"
    target = _asset("tgt")
    target["responsibility_scope"] = "Reports"
    assert _merge_plan(source, target)["conflicts"] != []


def test_agent_update_accepts_governance_fields() -> None:
    update = AgentUpdate(responsibility_scope="Scope", owner_label="Owner", acceptance_criteria=["A", "B"])
    assert update.responsibility_scope == "Scope"
    assert update.acceptance_criteria == ["A", "B"]


def test_agent_update_rejects_oversized_governance_fields() -> None:
    try:
        AgentUpdate(acceptance_criteria=[f"item-{i}" for i in range(21)])
    except ValidationError:
        return
    raise AssertionError("acceptance_criteria over 20 items must be rejected")
