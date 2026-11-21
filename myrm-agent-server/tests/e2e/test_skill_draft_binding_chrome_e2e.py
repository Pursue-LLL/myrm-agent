"""Real Chrome MCP E2E: an approved skill draft ends up bound to its agent, also when many are approved at once.

[INPUT]
- app.api.skills.test_fixtures (POS: Dev-only skills fixture router for Chrome E2E (prebuilt catalog, skill-manage and upstream-update seeds, growth drafts); gated by is_local_mode())
- tests.support.chrome_mcp_e2e::(open_settings_subroute, wait_for_state, http_json, get_e2e_api_url) (POS: Shared real-Chrome MCP helpers for formal UI E2E tests)
- tests.e2e.test_skill_draft_approve_name_chrome_e2e::(_owned_agent, _enabled_local_ids, _script, _object, card scripts) (POS: Chrome E2E: approving a skill draft in the Instinct Inbox acts on the skill the draft's name points at)
- tests.e2e.test_skill_manage_undo_rollback_chrome_e2e::_fetch_skill_md (POS: Chrome E2E: Task Steps rollback restores SKILL.md from a real skill_mutation batch)

[OUTPUT]
- test_approving_a_draft_binds_the_skill_to_its_agent: the Approve click on the inbox card adds the skill's page id to
  the agent's skill_ids
- test_drafts_approved_at_the_same_time_are_all_bound_to_their_agent: several drafts of one agent approved through the
  API at the same instant leave every approved skill in that agent's skill_ids, none dropped
- test_a_clean_new_skill_is_applied_and_stamped_without_review: a review result for a new, clean skill is applied on its
  own and its record carries the time it was resolved
- test_a_draft_that_cannot_be_written_goes_back_to_review_and_can_be_approved_again: approving a draft whose name no
  skill can have is answered as not materialized, the draft is pending again with no resolution time and nothing is
  bound or enabled, and approving it again under a valid name writes and binds the skill
- test_a_refused_approval_in_the_inbox_says_why_and_keeps_the_draft: the Approve click on the card of such a draft
  shows the reason the server gave, and the card stays in the inbox with the draft still pending

[POS]
The reviewer model's output is the one input a test cannot choose, so review results are fed through the production
growth lifecycle by a test-only route; the draft record, the inbox, the approval write, the skill write and the agent's
binding are the product's own, on the server's real transaction policy. The binding is read back from the agent API;
the concurrent approvals are each sent once, so a contention failure is seen and not retried away.
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager

import pytest

from tests.e2e.test_skill_draft_approve_name_chrome_e2e import (
    _APPROVE_CLICK_JS,
    _CARD_GONE_JS,
    _CARD_SHOWN_JS,
    _enabled_local_ids,
    _object,
    _owned_agent,
    _script,
)
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import _fetch_skill_md
from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    http_json_once,
    open_settings_subroute,
    wait_for_state,
)

_SKILLS = "/api/v1/skills"
_AGENTS = "/api/v1/user-agents"
_MARKER_BEFORE = "marker-before-approval"
_MARKER_APPROVED = "marker-written-by-approval"
_APPROVED_AT_ONCE = 5

# The failure toast carries the server's reason but stays on screen for a few seconds only, so the page records it the
# moment it appears instead of leaving it to a poll that browser work queued up behind other sessions could miss.
_REFUSAL_WATCH_JS = """(() => {
  window.__inboxRefusalSeen = false;
  new MutationObserver(() => {
    if ((document.body.textContent || '').includes(__REASON__)) window.__inboxRefusalSeen = true;
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  return { armed: true };
})()"""

# Once the refusal was recorded, the draft's own card is still listed.
_REFUSAL_SHOWN_JS = """(() => {
  const names = Array.from(document.querySelectorAll('[data-testid="instinct-draft-card"]')).map(
    (node) => node.getAttribute('data-draft-name') || ''
  );
  return { ready: window.__inboxRefusalSeen === true && names.includes(__NAME__), names };
})()"""


def _agent_skill_ids(api_url: str, agent_id: str) -> list[str]:
    data = _object(_object(http_json("GET", f"{api_url}{_AGENTS}/{agent_id}")).get("data"))
    skill_ids = data.get("skill_ids")
    assert isinstance(skill_ids, list), data
    return [str(skill_id) for skill_id in skill_ids]


def _drafts_of(api_url: str, agent_id: str, status: str) -> dict[str, dict[str, object]]:
    """The agent's drafts in ``status``, by draft name."""
    listing = _object(http_json("GET", f"{api_url}{_SKILLS}/drafts?status={status}&limit=500"))
    drafts = listing.get("drafts")
    assert isinstance(drafts, list), listing
    return {str(draft.get("name")): draft for draft in map(_object, drafts) if draft.get("agent_id") == agent_id}


def _seed_skill(api_url: str, dir_name: str) -> str:
    seeded = _object(
        http_json(
            "POST",
            f"{api_url}{_SKILLS}/test/seed-growth-skill",
            body={"dir_name": dir_name, "skill_name": dir_name, "marker": _MARKER_BEFORE},
        )
    )
    return str(seeded["skill_id"])


def _feed_review_result(api_url: str, skill_name: str, agent_id: str) -> None:
    recorded = http_json(
        "POST",
        f"{api_url}{_SKILLS}/test/seed-review-result",
        body={"skill_name": skill_name, "agent_id": agent_id, "marker": _MARKER_APPROVED},
    )
    assert recorded == {"recorded": True}, recorded


@contextmanager
def _skills_to_clean_up(api_url: str, dir_names: list[str]) -> Iterator[None]:
    """Leave no skill behind that the test created or that an approval enabled."""
    enabled_before = _enabled_local_ids(api_url)
    try:
        yield
    finally:
        for skill_id in _enabled_local_ids(api_url) - enabled_before:
            http_json(
                "POST",
                f"{api_url}{_SKILLS}/{urllib.parse.quote(skill_id, safe='')}/disable",
                expected_statuses=frozenset({200, 404, 409}),
            )
        http_json("POST", f"{api_url}{_SKILLS}/test/cleanup-growth-skills", body={"dir_names": dir_names})


def _approve(api_url: str, draft_id: str, skill_name: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {} if skill_name is None else {"skill_name": skill_name}
    return _object(http_json("POST", f"{api_url}{_SKILLS}/drafts/{draft_id}/approve", body=body))


def _approve_at_once(api_url: str, draft_ids: list[str]) -> list[dict[str, object]]:
    """Approve every draft through the API, all requests released together.

    Each request is sent once: a retry of a 500 or 503 would hide the contention failure this is meant to expose.
    """
    start_line = threading.Barrier(len(draft_ids))

    def approve(draft_id: str) -> dict[str, object]:
        start_line.wait(timeout=60)
        status, answer = http_json_once("POST", f"{api_url}{_SKILLS}/drafts/{draft_id}/approve", body={}, timeout_sec=120.0)
        assert status == 200, (draft_id, status, answer)
        return _object(answer)

    with ThreadPoolExecutor(max_workers=len(draft_ids)) as pool:
        futures = [pool.submit(approve, draft_id) for draft_id in draft_ids]
        return [future.result() for future in futures]


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_approving_a_draft_binds_the_skill_to_its_agent() -> None:
    api_url = get_e2e_api_url()
    dir_name = f"bind-skill-{uuid.uuid4().hex[:8]}"
    with _skills_to_clean_up(api_url, [dir_name]):
        skill_id = _seed_skill(api_url, dir_name)
        with _owned_agent(api_url, uuid.uuid4().hex[:8]) as agent_id:
            assert skill_id not in _agent_skill_ids(api_url, agent_id)
            _feed_review_result(api_url, dir_name, agent_id)

            route = f"/settings/agents?agentId={agent_id}"
            page_url = f"{get_e2e_ui_url().rstrip('/')}{route}"
            with open_settings_subroute(route) as (client, page):
                wait_for_state(client, page, _script(_CARD_SHOWN_JS, dir_name), timeout_sec=120.0, page_url=page_url)
                clicked = client.evaluate(page, _script(_APPROVE_CLICK_JS, dir_name), timeout_sec=5.0)
                assert isinstance(clicked, dict) and clicked.get("clicked") is True, clicked
                wait_for_state(client, page, _script(_CARD_GONE_JS, dir_name), timeout_sec=90.0, page_url=page_url)

            assert skill_id in _agent_skill_ids(api_url, agent_id)
            assert _MARKER_APPROVED in _fetch_skill_md(api_url, skill_id)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_drafts_approved_at_the_same_time_are_all_bound_to_their_agent() -> None:
    api_url = get_e2e_api_url()
    suffix = uuid.uuid4().hex[:8]
    dir_names = [f"bind-batch-{suffix}-{index}" for index in range(_APPROVED_AT_ONCE)]
    with ExitStack() as stack:
        stack.enter_context(_skills_to_clean_up(api_url, dir_names))
        skill_ids = {dir_name: _seed_skill(api_url, dir_name) for dir_name in dir_names}
        agent_id = stack.enter_context(_owned_agent(api_url, suffix))
        for dir_name in dir_names:
            _feed_review_result(api_url, dir_name, agent_id)
        pending = _drafts_of(api_url, agent_id, "PENDING_REVIEW")
        assert set(pending) == set(dir_names), sorted(pending)

        approved = _approve_at_once(api_url, [str(pending[dir_name]["id"]) for dir_name in dir_names])

        assert all(result.get("materialized") is True for result in approved), approved
        bound = _agent_skill_ids(api_url, agent_id)
        assert [skill_id for skill_id in skill_ids.values() if skill_id not in bound] == [], (skill_ids, bound)
        assert set(_drafts_of(api_url, agent_id, "APPROVED")) == set(dir_names)
        assert _drafts_of(api_url, agent_id, "PENDING_REVIEW") == {}


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_a_clean_new_skill_is_applied_and_stamped_without_review() -> None:
    api_url = get_e2e_api_url()
    suffix = uuid.uuid4().hex[:8]
    skill_name = f"auto-applied-{suffix}"
    with _skills_to_clean_up(api_url, [skill_name]), _owned_agent(api_url, suffix) as agent_id:
        enabled_before = _enabled_local_ids(api_url)
        _feed_review_result(api_url, skill_name, agent_id)

        applied = _drafts_of(api_url, agent_id, "AUTO_APPLIED")
        assert set(applied) == {skill_name}, sorted(applied)
        assert applied[skill_name]["reviewed_at"] is not None, applied[skill_name]
        assert _drafts_of(api_url, agent_id, "PENDING_REVIEW") == {}
        (new_skill_id,) = _enabled_local_ids(api_url) - enabled_before
        assert _MARKER_APPROVED in _fetch_skill_md(api_url, new_skill_id)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_a_draft_that_cannot_be_written_goes_back_to_review_and_can_be_approved_again() -> None:
    api_url = get_e2e_api_url()
    suffix = uuid.uuid4().hex[:8]
    unwritable = f"9-unwritable-{suffix}"  # a skill name has to start with a letter
    renamed = f"renamed-skill-{suffix}"
    with _skills_to_clean_up(api_url, [renamed]), _owned_agent(api_url, suffix) as agent_id:
        enabled_before = _enabled_local_ids(api_url)
        bound_before = _agent_skill_ids(api_url, agent_id)
        _feed_review_result(api_url, unwritable, agent_id)

        held = _drafts_of(api_url, agent_id, "PENDING_REVIEW")
        assert set(held) == {unwritable}, sorted(held)
        draft_id = str(held[unwritable]["id"])

        refused = _approve(api_url, draft_id)

        assert refused.get("materialized") is False, refused
        pending_again = _drafts_of(api_url, agent_id, "PENDING_REVIEW")
        assert set(pending_again) == {unwritable}, sorted(pending_again)
        assert pending_again[unwritable]["reviewed_at"] is None, pending_again[unwritable]
        assert _drafts_of(api_url, agent_id, "APPROVED") == {}
        assert _agent_skill_ids(api_url, agent_id) == bound_before
        assert _enabled_local_ids(api_url) == enabled_before

        written = _approve(api_url, draft_id, renamed)

        assert written.get("materialized") is True, written
        (new_skill_id,) = _enabled_local_ids(api_url) - enabled_before
        assert new_skill_id in _agent_skill_ids(api_url, agent_id)
        assert _MARKER_APPROVED in _fetch_skill_md(api_url, new_skill_id)
        assert set(_drafts_of(api_url, agent_id, "APPROVED")) == {unwritable}
        assert _drafts_of(api_url, agent_id, "PENDING_REVIEW") == {}


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_a_refused_approval_in_the_inbox_says_why_and_keeps_the_draft() -> None:
    api_url = get_e2e_api_url()
    suffix = uuid.uuid4().hex[:8]
    unwritable = f"9-unwritable-{suffix}"  # a skill name has to start with a letter
    with _owned_agent(api_url, suffix) as agent_id:
        bound_before = _agent_skill_ids(api_url, agent_id)
        _feed_review_result(api_url, unwritable, agent_id)
        draft_id = str(_drafts_of(api_url, agent_id, "PENDING_REVIEW")[unwritable]["id"])
        # A refused approval puts the draft back, so asking once through the API gives the reason without changing it.
        reason = _approve(api_url, draft_id).get("error")
        assert isinstance(reason, str) and reason, reason

        route = f"/settings/agents?agentId={agent_id}"
        page_url = f"{get_e2e_ui_url().rstrip('/')}{route}"
        with open_settings_subroute(route) as (client, page):
            wait_for_state(client, page, _script(_CARD_SHOWN_JS, unwritable), timeout_sec=120.0, page_url=page_url)
            armed = client.evaluate(page, _REFUSAL_WATCH_JS.replace("__REASON__", json.dumps(reason)), timeout_sec=5.0)
            assert isinstance(armed, dict) and armed.get("armed") is True, armed
            clicked = client.evaluate(page, _script(_APPROVE_CLICK_JS, unwritable), timeout_sec=5.0)
            assert isinstance(clicked, dict) and clicked.get("clicked") is True, clicked
            wait_for_state(client, page, _script(_REFUSAL_SHOWN_JS, unwritable), timeout_sec=60.0, page_url=page_url)

        pending = _drafts_of(api_url, agent_id, "PENDING_REVIEW")
        assert set(pending) == {unwritable}, sorted(pending)
        assert pending[unwritable]["reviewed_at"] is None, pending[unwritable]
        assert _agent_skill_ids(api_url, agent_id) == bound_before
