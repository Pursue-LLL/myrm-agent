"""Real Chrome MCP E2E: approving an evolution proposal for a skill another agent owns forks it for the approving agent.

[INPUT]
- app.api.skills.test_fixtures_evolution (POS: Dev-only fixture for the evolution proposal review Chrome E2E; gated by is_local_mode())
- app.api.skills.test_fixtures (POS: Dev-only skills fixture router for Chrome E2E; seeds the skill the proposal evolves)
- tests.e2e.test_evolution_proposal_outcomes_chrome_e2e::(_Proposal, _decide_at_once) (POS: Real Chrome MCP E2E: the outcomes of an evolution proposal other than a plain approval)
- tests.e2e.test_evolution_proposal_approve_chrome_e2e::(_case, _object, _MARKER_ADDED, _MARKER_BEFORE, _SKILLS) (POS: Real Chrome MCP E2E: approving an evolution proposal in the Skill Growth dashboard applies it to the skill file)
- tests.e2e.test_skill_draft_binding_chrome_e2e::_agent_skill_ids (POS: Real Chrome MCP E2E: an approved skill draft ends up bound to its agent, also when many are approved at once)
- tests.e2e.test_skill_draft_approve_name_chrome_e2e::_owned_agent (POS: Chrome E2E: approving a skill draft in the Instinct Inbox acts on the skill the draft's name points at)
- tests.e2e.test_skill_manage_undo_rollback_chrome_e2e::_fetch_skill_md (POS: Chrome E2E: Task Steps rollback restores SKILL.md from a real skill_mutation batch)
- tests.support.chrome_mcp_e2e::(http_json, http_json_once, get_e2e_api_url) (POS: Shared real-Chrome MCP helpers for formal UI E2E tests)

[OUTPUT]
- test_approving_a_proposal_for_a_skill_another_agent_owns_forks_it_for_the_approving_agent: the approval is applied,
  the approving agent's binding moves from the owner's skill to a fork and the owner's file is untouched
- test_proposals_that_fork_for_one_agent_at_the_same_time_all_replace_their_skill_in_its_bindings: several forks
  approved at the same instant for one agent leave that agent bound to every fork and to none of the skills they copy

[POS]
The evolved content and the skill's owner are the inputs a test cannot choose, so a test-only route records the
proposals and stores each skill as another agent's own; the approval, the Copy-on-Write fork, its snapshot and the
rebinding of the approving agent are the product's own, on the server's real transaction policy. The concurrent
approvals are each sent once, so a contention failure is seen and not retried away.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.e2e.test_evolution_proposal_approve_chrome_e2e import (
    _MARKER_ADDED,
    _MARKER_BEFORE,
    _SKILLS,
    _case,
    _object,
)
from tests.e2e.test_evolution_proposal_outcomes_chrome_e2e import _decide_at_once, _Proposal
from tests.e2e.test_skill_draft_approve_name_chrome_e2e import _owned_agent
from tests.e2e.test_skill_draft_binding_chrome_e2e import _agent_skill_ids
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import _fetch_skill_md
from tests.support.chrome_mcp_e2e import get_e2e_api_url, http_json, http_json_once

_AGENTS = "/api/v1/user-agents"
_EVOLUTION = "/api/v1/evolution"
_OWNER = "e2e-fork-owner"
_FORKED_AT_ONCE = 4


@contextmanager
def _forkable_proposals(api_url: str, agent_id: str, count: int) -> Iterator[list[_Proposal]]:
    """``count`` skills owned by another agent, all bound to ``agent_id``, each with a pending proposal from it.

    Whatever is left pending is rejected, and every skill directory is removed, the forks' included.
    """
    suffix = uuid.uuid4().hex[:8]
    dir_names = [f"fork-source-{suffix}-{index}" for index in range(count)]
    proposals: list[_Proposal] = []
    try:
        for dir_name in dir_names:
            seeded = _object(
                http_json(
                    "POST",
                    f"{api_url}{_SKILLS}/test/seed-growth-skill",
                    body={"dir_name": dir_name, "skill_name": dir_name, "marker": _MARKER_BEFORE},
                )
            )
            proposal = _object(
                http_json(
                    "POST",
                    f"{api_url}{_SKILLS}/test/seed-evolution-proposal",
                    body={"dir_name": dir_name, "marker": _MARKER_ADDED, "agent_id": agent_id, "owner_agent_id": _OWNER},
                )
            )
            assert proposal["skill_id"] == seeded["skill_id"], (proposal, seeded)
            proposals.append(_Proposal(dir_name, str(seeded["skill_id"]), str(proposal["evolution_id"])))
        http_json("PUT", f"{api_url}{_AGENTS}/{agent_id}", body={"skill_ids": [proposal.skill_id for proposal in proposals]})
        assert _agent_skill_ids(api_url, agent_id) == [proposal.skill_id for proposal in proposals]
        yield proposals
    finally:
        for proposal in proposals:
            # A settled proposal answers 409 and stays as it is; the status is of no interest here.
            http_json_once("POST", f"{api_url}{_EVOLUTION}/pending/{proposal.evolution_id}/reject")
        removable = [*dir_names, *(f"{dir_name}-fork" for dir_name in dir_names)]
        http_json("POST", f"{api_url}{_SKILLS}/test/cleanup-growth-skills", body={"dir_names": removable})


def _assert_owner_file_untouched(api_url: str, proposal: _Proposal) -> None:
    owners_file = _fetch_skill_md(api_url, proposal.skill_id)
    assert _MARKER_BEFORE in owners_file and _MARKER_ADDED not in owners_file, owners_file


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_approving_a_proposal_for_a_skill_another_agent_owns_forks_it_for_the_approving_agent() -> None:
    api_url = get_e2e_api_url()
    with (
        _owned_agent(api_url, uuid.uuid4().hex[:8]) as agent_id,
        _forkable_proposals(api_url, agent_id, 1) as (proposal,),
    ):
        status, answer = http_json_once(
            "POST", f"{api_url}{_EVOLUTION}/pending/{proposal.evolution_id}/approve", timeout_sec=120.0
        )

        assert (status, _object(answer).get("apply_status")) == (200, "APPLIED"), (status, answer)
        (bound,) = _agent_skill_ids(api_url, agent_id)
        assert bound.startswith("fork_") and bound != proposal.skill_id, bound
        assert _case(api_url, proposal.case_id)["apply_status"] == "APPLIED"
        _assert_owner_file_untouched(api_url, proposal)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_proposals_that_fork_for_one_agent_at_the_same_time_all_replace_their_skill_in_its_bindings() -> None:
    api_url = get_e2e_api_url()
    with (
        _owned_agent(api_url, uuid.uuid4().hex[:8]) as agent_id,
        _forkable_proposals(api_url, agent_id, _FORKED_AT_ONCE) as proposals,
    ):
        answers = _decide_at_once(api_url, [(proposal, "approve") for proposal in proposals])

        assert [(status, answer.get("apply_status")) for status, answer in answers] == [(200, "APPLIED")] * _FORKED_AT_ONCE, (
            answers
        )
        bound = _agent_skill_ids(api_url, agent_id)
        assert len(set(bound)) == _FORKED_AT_ONCE and all(skill_id.startswith("fork_") for skill_id in bound), bound
        for proposal in proposals:
            _assert_owner_file_untouched(api_url, proposal)
