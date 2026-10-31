"""Real Chrome MCP E2E: approving a skill draft in the Instinct Inbox acts on the skill the draft's name points at.

[INPUT]
- app.api.skills.test_fixtures (POS: Dev-only skills fixture router for Chrome E2E (prebuilt catalog, skill-manage and upstream-update seeds, growth drafts); gated by is_local_mode())
- tests.support.chrome_mcp_e2e::(open_settings_subroute, wait_for_state, http_json, get_e2e_api_url) (POS: Shared real-Chrome MCP helpers for formal UI E2E tests)
- tests.e2e.test_skill_manage_undo_rollback_chrome_e2e::_fetch_skill_md (POS: Chrome E2E: Task Steps rollback restores SKILL.md from a real skill_mutation batch)

[OUTPUT]
- test_approving_a_draft_spelled_unlike_a_skill_acts_on_that_skill_when_the_volume_ignores_case: the draft is recorded
  under the skill's directory name exactly when the volume opens that directory under the draft's spelling, and the
  inbox's Approve button then rewrites that skill and enables its own page id
- test_approving_a_draft_leaves_a_skill_it_only_resembles_untouched: a draft whose name leads to another directory is
  recorded as it is, and Approve creates that directory beside the skill

[POS]
The reviewer model's name for a draft is the one input a test cannot choose, so the review result is fed through the
production growth lifecycle by a test-only route; the skill lookup, the draft record, the inbox, the Approve click, the
approval write and the skill's page id are all real. The expectation is derived from the volume, so the test holds on a
case-sensitive and on a case-insensitive file system.
"""

from __future__ import annotations

import json
import urllib.parse
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import pytest

from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import _fetch_skill_md
from tests.support.chrome_mcp_e2e import get_e2e_api_url, http_json, open_settings_subroute, wait_for_state

_SKILLS = "/api/v1/skills"
_MARKER_BEFORE = "marker-before-approval"
_MARKER_APPROVED = "marker-written-by-approval"

_CARD_SHOWN_JS = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore
  }
  const panel = document.querySelector('[data-testid="instinct-inbox-panel"]');
  const empty = document.querySelector('[data-testid="instinct-inbox-empty"]');
  if (!panel && !empty) {
    const tab = Array.from(document.querySelectorAll('button,[role="tab"]')).find((button) =>
      /洞察|Insights/i.test(button.textContent || '')
    );
    if (tab) tab.click();
  }
  const names = Array.from(document.querySelectorAll('[data-testid="instinct-draft-card"]')).map(
    (card) => card.getAttribute('data-draft-name') || ''
  );
  return { ready: names.includes(__NAME__), names };
})()"""

_APPROVE_CLICK_JS = """(() => {
  const card = Array.from(document.querySelectorAll('[data-testid="instinct-draft-card"]')).find(
    (node) => node.getAttribute('data-draft-name') === __NAME__
  );
  const button = card && card.querySelector('[data-testid="instinct-approve-btn"]');
  if (!button) return { clicked: false };
  button.click();
  return { clicked: true };
})()"""

_CARD_GONE_JS = """(() => {
  const names = Array.from(document.querySelectorAll('[data-testid="instinct-draft-card"]')).map(
    (node) => node.getAttribute('data-draft-name') || ''
  );
  return { ready: !names.includes(__NAME__), names };
})()"""


@dataclass(frozen=True)
class ApprovalFacts:
    """What the skills directory and the skill configuration held after Approve was pressed on the draft's card."""

    volume_ignores_case: bool
    existing_id: str
    existing_skill_md: str
    new_enabled_ids: frozenset[str]
    new_skill_mds: dict[str, str]


def _script(template: str, name: str) -> str:
    return template.replace("__NAME__", json.dumps(name))


def _object(payload: object) -> dict[str, object]:
    assert isinstance(payload, dict), payload
    return payload


def _enabled_local_ids(api_url: str) -> set[str]:
    ids = _object(http_json("GET", f"{api_url}{_SKILLS}/config")).get("enabled_local_skill_ids")
    assert isinstance(ids, list)
    return {str(item) for item in ids}


@contextmanager
def _owned_agent(api_url: str, suffix: str) -> Iterator[str]:
    """An agent of the test's own: the draft lands in its inbox and Approve binds the skill to nobody else."""
    created = _object(
        http_json(
            "POST",
            f"{api_url}/api/v1/user-agents",
            body={"name": f"Draft Approve E2E {suffix}", "description": "Skill draft approval probe"},
        )
    )
    data = created.get("data")
    agent_id = data.get("id") if isinstance(data, dict) else None
    assert isinstance(agent_id, str) and agent_id, created
    try:
        yield agent_id
    finally:
        http_json("DELETE", f"{api_url}/api/v1/user-agents/{agent_id}", expected_statuses=frozenset({200, 204, 404}))


def _approve_in_the_inbox(
    *, dir_name: str, skill_name: str, card_name_if_volume_ignores_case: str, directories_to_remove: list[str]
) -> ApprovalFacts:
    """Seed a skill and a review result for ``skill_name``, press Approve on the draft's card, report what changed."""
    api_url = get_e2e_api_url()
    enabled_before = _enabled_local_ids(api_url)
    try:
        seeded = _object(
            http_json(
                "POST",
                f"{api_url}{_SKILLS}/test/seed-growth-skill",
                body={"dir_name": dir_name, "skill_name": skill_name, "marker": _MARKER_BEFORE},
            )
        )
        existing_id = str(seeded["skill_id"])
        ignores_case = seeded["volume_ignores_case"] is True
        card_name = card_name_if_volume_ignores_case if ignores_case else skill_name

        with _owned_agent(api_url, uuid.uuid4().hex[:8]) as agent_id:
            recorded = http_json(
                "POST",
                f"{api_url}{_SKILLS}/test/seed-review-result",
                body={"skill_name": skill_name, "agent_id": agent_id, "marker": _MARKER_APPROVED},
            )
            assert recorded == {"recorded": True}, recorded

            with open_settings_subroute(f"/settings/agents?agentId={agent_id}") as (client, page):
                wait_for_state(client, page, _script(_CARD_SHOWN_JS, card_name), timeout_sec=120.0)
                clicked = client.evaluate(page, _script(_APPROVE_CLICK_JS, card_name), timeout_sec=5.0)
                assert isinstance(clicked, dict) and clicked.get("clicked") is True, clicked
                wait_for_state(client, page, _script(_CARD_GONE_JS, card_name), timeout_sec=90.0)

        new_ids = frozenset(_enabled_local_ids(api_url) - enabled_before)
        return ApprovalFacts(
            volume_ignores_case=ignores_case,
            existing_id=existing_id,
            existing_skill_md=_fetch_skill_md(api_url, existing_id),
            new_enabled_ids=new_ids,
            new_skill_mds={skill_id: _fetch_skill_md(api_url, skill_id) for skill_id in new_ids},
        )
    finally:
        for skill_id in _enabled_local_ids(api_url) - enabled_before:
            http_json(
                "POST",
                f"{api_url}{_SKILLS}/{urllib.parse.quote(skill_id, safe='')}/disable",
                expected_statuses=frozenset({200, 404, 409}),
            )
        http_json(
            "POST",
            f"{api_url}{_SKILLS}/test/cleanup-growth-skills",
            body={"dir_names": [dir_name, *directories_to_remove]},
        )


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_approving_a_draft_spelled_unlike_a_skill_acts_on_that_skill_when_the_volume_ignores_case() -> None:
    suffix = uuid.uuid4().hex[:8]
    dir_name = f"report-builder-{suffix}"
    skill_name = f"Report-Builder-{suffix}"

    facts = _approve_in_the_inbox(
        dir_name=dir_name,
        skill_name=skill_name,
        card_name_if_volume_ignores_case=dir_name,
        directories_to_remove=[skill_name],
    )

    if facts.volume_ignores_case:
        # Approve wrote into the skill that is there, and what it enabled is that skill's own page id.
        assert facts.new_enabled_ids == {facts.existing_id}
        assert _MARKER_APPROVED in facts.existing_skill_md
        assert _MARKER_BEFORE not in facts.existing_skill_md
    else:
        # A volume that tells the spellings apart: a directory of the draft's own name is created, the skill is left alone.
        assert len(facts.new_enabled_ids) == 1 and facts.existing_id not in facts.new_enabled_ids
        assert _MARKER_BEFORE in facts.existing_skill_md
        assert _MARKER_APPROVED not in facts.existing_skill_md


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_approving_a_draft_leaves_a_skill_it_only_resembles_untouched() -> None:
    suffix = uuid.uuid4().hex[:8]
    dir_name = f"report-builder-{suffix}"
    skill_name = f"report builder {suffix} v2"

    facts = _approve_in_the_inbox(
        dir_name=dir_name,
        skill_name=skill_name,
        card_name_if_volume_ignores_case=skill_name,
        directories_to_remove=[f"report-builder-{suffix}-v2"],
    )

    assert _MARKER_BEFORE in facts.existing_skill_md
    assert _MARKER_APPROVED not in facts.existing_skill_md
    assert len(facts.new_enabled_ids) == 1 and facts.existing_id not in facts.new_enabled_ids
    (sibling_md,) = facts.new_skill_mds.values()
    assert _MARKER_APPROVED in sibling_md
