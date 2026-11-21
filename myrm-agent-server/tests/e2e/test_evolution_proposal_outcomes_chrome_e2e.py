"""Real Chrome MCP E2E: the outcomes of an evolution proposal other than a plain approval.

[INPUT]
- app.api.skills.test_fixtures_evolution (POS: Dev-only fixture for the evolution proposal review Chrome E2E; gated by is_local_mode())
- app.api.skills.test_fixtures (POS: Dev-only skills fixture router for Chrome E2E (prebuilt catalog, skill-manage and upstream-update seeds, growth drafts); gated by is_local_mode())
- tests.e2e.test_evolution_proposal_approve_chrome_e2e::(_script, _case, _object, card scripts) (POS: Real Chrome MCP E2E: approving an evolution proposal in the Skill Growth dashboard applies it to the skill file)
- tests.e2e.test_skill_manage_undo_rollback_chrome_e2e::_fetch_skill_md (POS: Chrome E2E: Task Steps rollback restores SKILL.md from a real skill_mutation batch)
- tests.support.chrome_mcp_e2e::(open_settings_subroute, wait_for_state, http_json, http_json_once, get_e2e_api_url, get_e2e_ui_url) (POS: Shared real-Chrome MCP helpers for formal UI E2E tests)

[OUTPUT]
- test_a_proposal_for_a_skill_edited_since_is_refused_and_can_be_discarded: after the skill is edited through the
  settings editor's save route, the Approve click leaves the card in APPLY_FAILED with the stale-base reason and
  without an Approve button, the user's edit intact on disk; discarding the card then rejects the proposal
- test_rejecting_a_proposal_with_a_reason_records_the_reason: the two-step Reject click on a pending card stores the
  typed reason as the case's remediation and leaves the skill file as it was
- test_a_revised_proposal_applies_the_revision_and_is_rolled_back_once: the revision, not the first draft, is what
  the approval writes; the rollback restores the original text and a second rollback is refused
- test_proposals_decided_at_the_same_time_are_settled_exactly_once: an approve racing a reject on the same proposal
  and two approves of the same proposal, each sent once, leave one consistent outcome per proposal

[POS]
The evolved content is the one input a test cannot choose, so a test-only route records the proposal through the
production creation path; the dashboard, the clicks, the approval and rejection settlements, the apply, the rollback
and the file reads are the product's own. The race test sends each request once, so a contention failure is seen
and not retried away.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

import pytest

from tests.e2e.test_evolution_proposal_approve_chrome_e2e import (
    _APPROVE_CLICK_JS,
    _CARD_STATUS_JS,
    _MARKER_ADDED,
    _MARKER_BEFORE,
    _PENDING_ROUTE,
    _SKILLS,
    _case,
    _object,
    _script,
)
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import _fetch_skill_md
from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    http_json_once,
    open_settings_subroute,
    wait_for_state,
)

_EVOLUTION = "/api/v1/evolution"
_MARKER_EDITED = "marker-written-by-the-user"
_MARKER_REVISED = "marker-written-by-the-reviewer"
_REJECT_REASON = "e2e-reason: this step does not belong in the skill"
_CONTESTED_PROPOSALS = 4

# A card the apply refused: it keeps the Reject button and, because retrying cannot help, loses the Approve one.
_REFUSED_CARD_JS = """(() => {
  const card = __CARD__;
  const status = card ? card.getAttribute('data-case-status') : null;
  const approve = Boolean(card && card.querySelector('[data-testid="growth-case-approve-btn"]'));
  const reject = Boolean(card && card.querySelector('[data-testid="growth-case-reject-btn"]'));
  return { ready: status === 'APPLY_FAILED' && !approve && reject, status, approve, reject };
})()"""

_REJECT_CLICK_JS = """(() => {
  const card = __CARD__;
  const button = card && card.querySelector('[data-testid="growth-case-reject-btn"]');
  if (!button || button.disabled) return { clicked: false };
  button.click();
  return { clicked: true };
})()"""

# The reason box is a controlled textarea, so the value goes in through the native setter and an input event.
_REASON_TYPED_JS = """(() => {
  const card = __CARD__;
  const field = card && card.querySelector('textarea');
  if (!field) return { ready: false };
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(field, __REASON__);
  field.dispatchEvent(new Event('input', { bubbles: true }));
  return { ready: field.value === __REASON__ };
})()"""


@dataclass(frozen=True)
class _Proposal:
    dir_name: str
    skill_id: str
    evolution_id: str

    @property
    def case_id(self) -> str:
        return f"evolution:{self.evolution_id}"


@contextmanager
def _seeded_proposal(api_url: str) -> Iterator[_Proposal]:
    """A skill with a pending proposal for it; whatever the test leaves pending is rejected and the skill removed."""
    dir_name = f"evolution-outcome-{uuid.uuid4().hex[:8]}"
    evolution_id = ""
    try:
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
                body={"dir_name": dir_name, "marker": _MARKER_ADDED},
            )
        )
        evolution_id = str(proposal["evolution_id"])
        assert proposal["skill_id"] == seeded["skill_id"], (proposal, seeded)
        yield _Proposal(dir_name, str(seeded["skill_id"]), evolution_id)
    finally:
        if evolution_id:
            # A settled proposal answers 409 and stays as it is; the status is of no interest here.
            http_json_once("POST", f"{api_url}{_EVOLUTION}/pending/{evolution_id}/reject")
        http_json("POST", f"{api_url}{_SKILLS}/test/cleanup-growth-skills", body={"dir_names": [dir_name]})


def _click(client: ChromeMcpClient, page: McpPage, template: str, case_id: str) -> None:
    clicked = client.evaluate(page, _script(template, case_id), timeout_sec=5.0)
    assert isinstance(clicked, dict) and clicked.get("clicked") is True, clicked


def _reject_through_card(client: ChromeMcpClient, page: McpPage, case_id: str, reason: str, page_url: str) -> None:
    """The two-step rejection of an evolution case: the first click opens the reason box, the second one confirms."""
    _click(client, page, _REJECT_CLICK_JS, case_id)
    typed = _script(_REASON_TYPED_JS, case_id).replace("__REASON__", json.dumps(reason))
    wait_for_state(client, page, typed, timeout_sec=30.0, page_url=page_url)
    _click(client, page, _REJECT_CLICK_JS, case_id)


def _decide_at_once(api_url: str, decisions: list[tuple[_Proposal, str]]) -> list[tuple[int, dict[str, object]]]:
    """Send every decision (``approve`` or ``reject``) once, all released together; answers keep the request order."""
    start_line = threading.Barrier(len(decisions))

    def send(proposal: _Proposal, action: str) -> tuple[int, dict[str, object]]:
        start_line.wait(timeout=60)
        status, answer = http_json_once(
            "POST", f"{api_url}{_EVOLUTION}/pending/{proposal.evolution_id}/{action}", timeout_sec=120.0
        )
        return status, _object(answer)

    with ThreadPoolExecutor(max_workers=len(decisions)) as pool:
        futures = [pool.submit(send, proposal, action) for proposal, action in decisions]
        return [future.result() for future in futures]


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_a_proposal_for_a_skill_edited_since_is_refused_and_can_be_discarded() -> None:
    api_url = get_e2e_api_url()
    with _seeded_proposal(api_url) as proposal:
        edited = f"---\nname: {proposal.dir_name}\ndescription: Build the weekly report.\n---\n\n## Steps\n1. {_MARKER_EDITED}\n"
        saved = _object(http_json("PUT", f"{api_url}{_SKILLS}/{proposal.skill_id}/files/SKILL.md", body={"content": edited}))
        assert saved["status"] == "ok", saved

        page_url = f"{get_e2e_ui_url().rstrip('/')}{_PENDING_ROUTE}"
        with open_settings_subroute(_PENDING_ROUTE) as (client, page):
            pending = _script(_CARD_STATUS_JS, proposal.case_id, "PENDING_REVIEW")
            wait_for_state(client, page, pending, timeout_sec=120.0, page_url=page_url)
            _click(client, page, _APPROVE_CLICK_JS, proposal.case_id)
            refused_card = _script(_REFUSED_CARD_JS, proposal.case_id)
            wait_for_state(client, page, refused_card, timeout_sec=90.0, page_url=page_url)

            refused = _case(api_url, proposal.case_id)
            assert (refused["status"], refused["apply_status"], refused["reason_code"]) == (
                "APPLY_FAILED",
                "FAILED",
                "stale_base",
            ), refused
            skill_md = _fetch_skill_md(api_url, proposal.skill_id)
            assert _MARKER_EDITED in skill_md and _MARKER_ADDED not in skill_md, skill_md

            _reject_through_card(client, page, proposal.case_id, "", page_url)
            discarded_card = _script(_CARD_STATUS_JS, proposal.case_id, "REJECTED")
            wait_for_state(client, page, discarded_card, timeout_sec=90.0, page_url=page_url)

        discarded = _case(api_url, proposal.case_id)
        assert (discarded["status"], discarded["reason_code"]) == ("REJECTED", "rejected"), discarded
        skill_md = _fetch_skill_md(api_url, proposal.skill_id)
        assert _MARKER_EDITED in skill_md and _MARKER_ADDED not in skill_md, skill_md


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_rejecting_a_proposal_with_a_reason_records_the_reason() -> None:
    api_url = get_e2e_api_url()
    with _seeded_proposal(api_url) as proposal:
        page_url = f"{get_e2e_ui_url().rstrip('/')}{_PENDING_ROUTE}"
        with open_settings_subroute(_PENDING_ROUTE) as (client, page):
            pending = _script(_CARD_STATUS_JS, proposal.case_id, "PENDING_REVIEW")
            wait_for_state(client, page, pending, timeout_sec=120.0, page_url=page_url)
            _reject_through_card(client, page, proposal.case_id, _REJECT_REASON, page_url)
            rejected_card = _script(_CARD_STATUS_JS, proposal.case_id, "REJECTED")
            wait_for_state(client, page, rejected_card, timeout_sec=90.0, page_url=page_url)

        rejected = _case(api_url, proposal.case_id)
        assert (
            rejected["status"],
            rejected["apply_status"],
            rejected["reason_code"],
            rejected["remediation"],
        ) == ("REJECTED", "NOT_APPLIED", "rejected", _REJECT_REASON), rejected
        skill_md = _fetch_skill_md(api_url, proposal.skill_id)
        assert _MARKER_BEFORE in skill_md and _MARKER_ADDED not in skill_md, skill_md


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_a_revised_proposal_applies_the_revision_and_is_rolled_back_once() -> None:
    api_url = get_e2e_api_url()
    pending_url = f"{api_url}{_EVOLUTION}/pending"
    with _seeded_proposal(api_url) as proposal:
        drafted = _object(http_json("GET", f"{pending_url}/{proposal.evolution_id}"))
        revised = f"{str(drafted['original_content']).rstrip()}\n2. {_MARKER_REVISED}\n"
        revision = _object(http_json("PATCH", f"{pending_url}/{proposal.evolution_id}/revise", body={"evolved_content": revised}))
        assert revision["status"] == "PENDING_REVIEW", revision
        assert _object(http_json("GET", f"{pending_url}/{proposal.evolution_id}"))["evolved_content"] == revised

        approval = _object(http_json("POST", f"{pending_url}/{proposal.evolution_id}/approve", timeout_sec=120.0))
        assert (approval["status"], approval["apply_status"]) == ("approved", "APPLIED"), approval
        applied = _fetch_skill_md(api_url, proposal.skill_id)
        assert _MARKER_BEFORE in applied and _MARKER_REVISED in applied and _MARKER_ADDED not in applied, applied

        rollback_url = f"{api_url}{_EVOLUTION}/{proposal.evolution_id}/rollback"
        rolled_back = _object(http_json("POST", rollback_url, timeout_sec=120.0))
        assert rolled_back["status"] == "rolled_back", rolled_back
        restored = _fetch_skill_md(api_url, proposal.skill_id)
        assert _MARKER_BEFORE in restored and _MARKER_REVISED not in restored, restored
        assert _case(api_url, proposal.case_id)["apply_status"] == "ROLLED_BACK"

        status, answer = http_json_once("POST", rollback_url, timeout_sec=120.0)
        assert status == 409, (status, answer)
        assert _fetch_skill_md(api_url, proposal.skill_id) == restored


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_proposals_decided_at_the_same_time_are_settled_exactly_once() -> None:
    api_url = get_e2e_api_url()
    with ExitStack() as stack:
        contested = [stack.enter_context(_seeded_proposal(api_url)) for _ in range(_CONTESTED_PROPOSALS)]
        answers = _decide_at_once(api_url, [(proposal, action) for proposal in contested for action in ("approve", "reject")])
        for index, proposal in enumerate(contested):
            (approve_status, approve_answer), (reject_status, reject_answer) = answers[2 * index : 2 * index + 2]
            settled = _case(api_url, proposal.case_id)
            skill_md = _fetch_skill_md(api_url, proposal.skill_id)
            # What a failed assertion has to show: pytest cuts a long message, so the case is cut down to what decides it.
            report = {
                "proposal": index,
                "status": settled["status"],
                "apply_status": settled["apply_status"],
                "approve": (approve_status, approve_answer.get("status") or approve_answer.get("detail")),
                "reject": (reject_status, reject_answer.get("status") or reject_answer.get("detail")),
                "apply_error": str(settled["apply_error"])[:100],
            }
            if settled["status"] == "APPROVED":
                assert (approve_status, reject_status, settled["apply_status"]) == (200, 409, "APPLIED"), report
                assert _MARKER_ADDED in skill_md, report
            else:
                assert (settled["status"], reject_status, approve_status) == ("REJECTED", 200, 409), report
                assert _MARKER_ADDED not in skill_md, report

        twice = [stack.enter_context(_seeded_proposal(api_url)) for _ in range(_CONTESTED_PROPOSALS)]
        answers = _decide_at_once(api_url, [(proposal, "approve") for proposal in twice for _ in range(2)])
        for index, proposal in enumerate(twice):
            pair = [
                (status, answer.get("apply_status") or answer.get("detail"))
                for status, answer in answers[2 * index : 2 * index + 2]
            ]
            assert pair == [(200, "APPLIED")] * 2, (index, pair)
            applied = _fetch_skill_md(api_url, proposal.skill_id)
            assert applied.count(_MARKER_ADDED) == 1, applied
            # The repeated apply left the record able to undo itself: the rollback still has the original text.
            rollback = _object(http_json("POST", f"{api_url}{_EVOLUTION}/{proposal.evolution_id}/rollback", timeout_sec=120.0))
            assert rollback["status"] == "rolled_back", rollback
            restored = _fetch_skill_md(api_url, proposal.skill_id)
            assert _MARKER_BEFORE in restored and _MARKER_ADDED not in restored, restored
