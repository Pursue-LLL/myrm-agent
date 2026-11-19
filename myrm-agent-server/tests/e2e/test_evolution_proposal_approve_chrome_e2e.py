"""Real Chrome MCP E2E: approving an evolution proposal in the Skill Growth dashboard applies it to the skill file.

[INPUT]
- app.api.skills.test_fixtures_evolution (POS: Dev-only fixture for the evolution proposal review Chrome E2E; gated by is_local_mode())
- app.api.skills.test_fixtures (POS: Dev-only skills fixture router for Chrome E2E; seeds the skill the proposal evolves)
- tests.support.chrome_mcp_e2e::(open_settings_subroute, wait_for_state, http_json, get_e2e_api_url, get_e2e_ui_url) (POS: Shared real-Chrome MCP helpers for formal UI E2E tests)
- tests.e2e.test_skill_manage_undo_rollback_chrome_e2e::_fetch_skill_md (POS: Chrome E2E: Task Steps rollback restores SKILL.md from a real skill_mutation batch)

[OUTPUT]
- test_approving_an_evolution_proposal_applies_it_to_the_skill: the proposal's card in Settings > Skills goes from
  PENDING_REVIEW to APPROVED on the Approve click, the case then reads APPLIED, and the skill's SKILL.md, which lacked
  the step the proposal adds until then, carries it next to the step it had

[POS]
The evolved content is the one input a test cannot choose, so a test-only route records the proposal through the
production creation path; the dashboard, the Approve click, the approval settlement, the apply to the file and the
read back are the product's own.
"""

from __future__ import annotations

import json
import urllib.parse
import uuid

import pytest

from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import _fetch_skill_md
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    wait_for_state,
)

_SKILLS = "/api/v1/skills"
_PENDING_ROUTE = "/settings/skills?sub=pending"
_MARKER_BEFORE = "marker-before-evolution"
_MARKER_ADDED = "marker-added-by-evolution"

# The case id holds a colon, so the card is matched on the attribute value in JS instead of through a CSS selector.
_FIND_CARD_JS = (
    "Array.from(document.querySelectorAll('[data-testid=\"growth-case-card\"]'))"
    ".find((el) => el.getAttribute('data-case-id') === __CASE_ID__)"
)

_CARD_STATUS_JS = """(() => {
  const card = __CARD__;
  const status = card ? card.getAttribute('data-case-status') : null;
  return { ready: status === __STATUS__, status };
})()"""

_APPROVE_CLICK_JS = """(() => {
  const card = __CARD__;
  const button = card && card.querySelector('[data-testid="growth-case-approve-btn"]');
  if (!button || button.disabled) return { clicked: false };
  button.click();
  return { clicked: true };
})()"""


def _script(template: str, case_id: str, status: str = "") -> str:
    return (
        template.replace("__CARD__", _FIND_CARD_JS)
        .replace("__CASE_ID__", json.dumps(case_id))
        .replace("__STATUS__", json.dumps(status))
    )


def _object(payload: object) -> dict[str, object]:
    assert isinstance(payload, dict), payload
    return payload


def _case(api_url: str, case_id: str) -> dict[str, object]:
    payload = _object(http_json("GET", f"{api_url}/api/v1/skill-growth/cases/{urllib.parse.quote(case_id, safe='')}"))
    return _object(payload.get("data"))


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_approving_an_evolution_proposal_applies_it_to_the_skill() -> None:
    api_url = get_e2e_api_url()
    dir_name = f"evolution-review-{uuid.uuid4().hex[:8]}"
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
        case_id = f"evolution:{evolution_id}"
        assert proposal["skill_id"] == seeded["skill_id"], (proposal, seeded)

        pending = _case(api_url, case_id)
        assert (pending["status"], pending["apply_status"]) == ("PENDING_REVIEW", "NOT_APPLIED"), pending
        assert _MARKER_ADDED not in _fetch_skill_md(api_url, str(seeded["skill_id"]))

        page_url = f"{get_e2e_ui_url().rstrip('/')}{_PENDING_ROUTE}"
        with open_settings_subroute(_PENDING_ROUTE) as (client, page):
            wait_for_state(
                client, page, _script(_CARD_STATUS_JS, case_id, "PENDING_REVIEW"), timeout_sec=120.0, page_url=page_url
            )
            clicked = client.evaluate(page, _script(_APPROVE_CLICK_JS, case_id), timeout_sec=5.0)
            assert isinstance(clicked, dict) and clicked.get("clicked") is True, clicked
            wait_for_state(client, page, _script(_CARD_STATUS_JS, case_id, "APPROVED"), timeout_sec=90.0, page_url=page_url)

        approved = _case(api_url, case_id)
        assert (approved["status"], approved["apply_status"]) == ("APPROVED", "APPLIED"), approved
        skill_md = _fetch_skill_md(api_url, str(seeded["skill_id"]))
        assert _MARKER_BEFORE in skill_md and _MARKER_ADDED in skill_md, skill_md
    finally:
        if evolution_id:
            # Leaves no pending proposal behind when the test stops before the approval; an applied one answers 409.
            http_json(
                "POST",
                f"{api_url}/api/v1/evolution/pending/{evolution_id}/reject",
                expected_statuses=frozenset({200, 404, 409}),
            )
        http_json("POST", f"{api_url}{_SKILLS}/test/cleanup-growth-skills", body={"dir_names": [dir_name]})
