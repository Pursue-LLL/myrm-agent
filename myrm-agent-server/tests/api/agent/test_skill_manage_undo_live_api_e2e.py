"""Live-stack API E2E: a live model saves a skill and the committed batch reaches the persisted Task Steps entry.

Task flow (no browser): a custom agent with only skill_manage mounted gets a plain request to save a skill; the
model calls ``skill_manage_tool``; the skill lands in the catalog with the SKILL.md the model sent; the server
announces the committed batch on the stream after the call's arguments and persists it on that step; rolling the
batch back (what the Undo dialog calls) removes the skill the batch created. A second flow rewrites that skill in a
later turn and expects the undo to bring back what the rewrite replaced instead of removing the skill. A third flow has
the model delete a skill: the skill is gone, the step is not a failure, and no batch is announced because a delete has
nothing to undo. A fourth flow patches a skill saved in an earlier turn, which the agent's own backend cannot see, and
expects the patch to land and its undo to put the text back.

Run::

    ./myrm test -m e2e myrm-agent/myrm-agent-server/tests/api/agent/test_skill_manage_undo_live_api_e2e.py
"""

from __future__ import annotations

import json
import uuid

import httpx
import pytest

from tests.api.agent.skill_manage_api_helpers import (
    FAILED_STATUSES,
    SAVE_TOOL,
    STEP_EVENT_TYPES,
    announced_batch,
    announced_batches,
    batch_id_of,
    catalog_skill_id,
    create_agent,
    create_chat,
    data,
    delete_request,
    isolated_backend_url,
    patch_request,
    persisted_skill_steps,
    requires_live_model,
    rewrite_request,
    skill_md,
    stored_batch_ids,
    stream_turn,
    user_request,
    wait_for,
)


@pytest.mark.e2e
@pytest.mark.timeout(600)
@requires_live_model
def test_live_agent_saves_a_skill_and_the_batch_reaches_its_step_and_rolls_back() -> None:
    backend_url = isolated_backend_url()
    suffix = uuid.uuid4().hex[:8]
    skill_name = f"api-manage-{suffix}"
    marker = f"API_MARKER_{suffix}"
    chat_id = f"apimanage{suffix}"

    with httpx.Client() as client:
        agent_id = create_agent(client, backend_url, suffix)
        create_chat(client, backend_url, chat_id, agent_id)
        events = stream_turn(client, backend_url, agent_id, chat_id, user_request(skill_name, marker))

        batch_events = [(index, batch_id_of(event)) for index, event in enumerate(events) if batch_id_of(event)]
        assert batch_events, f"the stream never announced a committed batch; types: {[e.get('type') for e in events][:40]}"
        announced_at, announced = batch_events[0]
        step_seen_at = next(
            (
                index
                for index, event in enumerate(events)
                if event.get("type") in STEP_EVENT_TYPES
                and SAVE_TOOL in json.dumps(event, default=str)
                and not batch_id_of(event)
            ),
            None,
        )
        print(f"E2E_BATCH_ANNOUNCED: batch={announced} step_event={step_seen_at} batch_event={announced_at}", flush=True)
        assert step_seen_at is not None and step_seen_at < announced_at, (
            f"the skill_manage step must reach the stream before its batch id: step={step_seen_at} batch={announced_at}"
        )

        stored = wait_for(
            lambda: stored_batch_ids(client, backend_url, chat_id), timeout_sec=60.0, what="the persisted step batch id"
        )
        assert announced in stored, f"persisted batch ids {stored} do not include the announced {announced}"
        persisted_steps = persisted_skill_steps(client, backend_url, chat_id)
        print(f"E2E_PERSISTED_STEP: {json.dumps(persisted_steps, sort_keys=True, default=str)}", flush=True)
        committed = next(step for step in persisted_steps if step.get("skill_mutation_batch_id") == announced)
        # The Chrome E2E seeds mirror this shape (_persisted_skill_manage_step); change both together.
        assert "status" not in committed and committed.get("step_key") == "skill_manage_tool_tool", committed
        assert committed.get("tool_call_id") and isinstance(committed.get("items"), list), committed

        skill_id = catalog_skill_id(client, backend_url, skill_name)
        assert skill_id, f"skill {skill_name!r} is not in the catalog after the live turn"
        saved = skill_md(client, backend_url, skill_id)
        assert marker in saved, f"the saved SKILL.md lost the marker the user asked for:\n{saved[:600]}"

        rollback_url = f"{backend_url}/api/v1/skill-optimization/mutations/{announced}/rollback"
        assert data(client.post(rollback_url, timeout=60.0)).get("status")
        wait_for(
            lambda: catalog_skill_id(client, backend_url, skill_name) is None,
            timeout_sec=60.0,
            what="the skill to disappear after the rollback",
        )


@pytest.mark.e2e
@pytest.mark.timeout(600)
@requires_live_model
def test_live_agent_rewrites_a_skill_and_the_undo_brings_back_what_it_replaced() -> None:
    backend_url = isolated_backend_url()
    suffix = uuid.uuid4().hex[:8]
    skill_name = f"api-rewrite-{suffix}"
    first_marker, second_marker = f"API_FIRST_{suffix}", f"API_SECOND_{suffix}"
    chat_id = f"apirewrite{suffix}"

    with httpx.Client() as client:
        agent_id = create_agent(client, backend_url, suffix)
        create_chat(client, backend_url, chat_id, agent_id)
        first = announced_batch(stream_turn(client, backend_url, agent_id, chat_id, user_request(skill_name, first_marker)))
        assert first, "the first save never announced a committed batch"
        skill_id = catalog_skill_id(client, backend_url, skill_name)
        assert skill_id, f"skill {skill_name!r} is not in the catalog after the first save"

        second = announced_batch(stream_turn(client, backend_url, agent_id, chat_id, rewrite_request(skill_name, second_marker)))
        assert second and second != first, f"the rewrite must commit its own batch: first={first} second={second}"
        rewritten = skill_md(client, backend_url, skill_id)
        assert second_marker in rewritten and first_marker not in rewritten, f"the rewrite did not land:\n{rewritten[:600]}"

        rollback_url = f"{backend_url}/api/v1/skill-optimization/mutations/{second}/rollback"
        assert data(client.post(rollback_url, timeout=60.0)).get("status")
        assert catalog_skill_id(client, backend_url, skill_name) == skill_id, "the undo of a rewrite removed the skill"
        restored = skill_md(client, backend_url, skill_id)
        assert first_marker in restored and second_marker not in restored, f"the undo kept the rewrite:\n{restored[:600]}"


@pytest.mark.e2e
@pytest.mark.timeout(600)
@requires_live_model
def test_live_agent_deletes_a_skill_for_good_and_offers_no_undo_for_it() -> None:
    backend_url = isolated_backend_url()
    suffix = uuid.uuid4().hex[:8]
    skill_name = f"api-delete-{suffix}"
    chat_id = f"apidelete{suffix}"

    with httpx.Client() as client:
        agent_id = create_agent(client, backend_url, suffix)
        create_chat(client, backend_url, chat_id, agent_id)
        saved = announced_batch(stream_turn(client, backend_url, agent_id, chat_id, user_request(skill_name, suffix)))
        assert saved, "the save never announced a committed batch"
        assert catalog_skill_id(client, backend_url, skill_name), f"skill {skill_name!r} is not in the catalog after the save"

        deleted_turn = stream_turn(client, backend_url, agent_id, chat_id, delete_request(skill_name))
        assert catalog_skill_id(client, backend_url, skill_name) is None, "the model's delete did not remove the skill"
        assert not announced_batches(deleted_turn) - {saved}, "a delete has nothing to undo, yet the stream announced a batch"

        delete_steps = [
            step
            for step in persisted_skill_steps(client, backend_url, chat_id)
            if "'delete'" in json.dumps(step.get("items"), default=str)
        ]
        assert delete_steps, "the persisted steps hold no delete call"
        assert all(
            step.get("status") not in FAILED_STATUSES and not step.get("skill_mutation_batch_id") for step in delete_steps
        ), f"a finished delete must be neither a failure nor an undo target: {delete_steps}"

        # The save's Undo is still on screen after the delete: pressing it is refused cleanly and nothing comes back.
        stale_undo = client.post(f"{backend_url}/api/v1/skill-optimization/mutations/{saved}/rollback", timeout=60.0)
        assert stale_undo.status_code == 409, f"undoing a save whose skill is gone must be a 409: {stale_undo.text[:300]}"
        assert catalog_skill_id(client, backend_url, skill_name) is None, "the stale undo brought the deleted skill back"


@pytest.mark.e2e
@pytest.mark.timeout(600)
@requires_live_model
def test_live_agent_patches_a_skill_it_saved_in_an_earlier_turn_and_the_undo_reverts_the_patch() -> None:
    backend_url = isolated_backend_url()
    suffix = uuid.uuid4().hex[:8]
    skill_name = f"api-patch-{suffix}"
    first_marker, second_marker = f"API_FIRST_{suffix}", f"API_SECOND_{suffix}"
    chat_id = f"apipatch{suffix}"

    with httpx.Client() as client:
        agent_id = create_agent(client, backend_url, suffix)
        create_chat(client, backend_url, chat_id, agent_id)
        assert announced_batch(stream_turn(client, backend_url, agent_id, chat_id, user_request(skill_name, first_marker)))
        skill_id = catalog_skill_id(client, backend_url, skill_name)
        assert skill_id, f"skill {skill_name!r} is not in the catalog after the save"

        patch_turn = stream_turn(client, backend_url, agent_id, chat_id, patch_request(skill_name, first_marker, second_marker))
        # The agent's own backend lists no skill outside its allowlist. A patch that reads only through it reports the
        # skill as missing: that batch is rolled back and carries no batch id, and the model can only fall back to a
        # full save. So the persisted step of the patch call holding a batch id is what proves the patch itself landed.
        patch_steps = [
            step
            for step in persisted_skill_steps(client, backend_url, chat_id)
            if "'patch'" in json.dumps(step.get("items"), default=str)
        ]
        assert patch_steps, "the model never called patch"
        patch_batch = patch_steps[-1].get("skill_mutation_batch_id")
        assert isinstance(patch_batch, str) and patch_batch, f"the patch call was not committed: {patch_steps}"
        assert patch_batch in announced_batches(patch_turn), "the stream never announced the patch's batch"
        patched = skill_md(client, backend_url, skill_id)
        assert second_marker in patched and first_marker not in patched, f"the patch did not land:\n{patched[:600]}"

        rollback_url = f"{backend_url}/api/v1/skill-optimization/mutations/{patch_batch}/rollback"
        assert data(client.post(rollback_url, timeout=60.0)).get("status")
        restored = skill_md(client, backend_url, skill_id)
        assert first_marker in restored and second_marker not in restored, f"the undo kept the patch:\n{restored[:600]}"
