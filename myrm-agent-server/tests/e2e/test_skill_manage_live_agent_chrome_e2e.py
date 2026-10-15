"""Chrome LIVE E2E: a live model saves a skill through skill_manage_tool and the user undoes it from Task Steps.

Nothing is seeded. The user types the request in the composer; the model calls ``skill_manage_tool``; the
skill lands in the catalog with the SKILL.md the model sent; the server attaches the batch id that the Task
Steps undo hint needs; the user opens the hint, confirms the rollback, and the skill the batch created is gone.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_skill_manage_live_agent_chrome_e2e.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    dump_backend_log_on_failure,
    snapshot_backend_log_offset,
    wait_e2e_provider_ready,
)

from tests.e2e.test_skill_manage_undo_hint_chrome_e2e import (  # noqa: E402
    _CLICK_OPEN_STEPS_JS,
    _HINT_READY_JS,
    _ROLLBACK_VISIBLE_JS,
    _STEPS_EXPANDED_JS,
)
from tests.e2e.test_skill_manage_undo_rollback_chrome_e2e import (  # noqa: E402
    _CONFIRM_ROLLBACK_JS,
    _TOAST_SUCCESS_JS,
    _fetch_skill_md,
)
from tests.support.chrome_mcp_e2e import (  # noqa: E402
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
    wait_for_state,
)
from tests.support.chrome_skill_hooks_composer import describe_page, drive_chat_turn  # noqa: E402
from tests.support.chrome_skill_hooks_live_e2e import SkillChat  # noqa: E402
from tests.support.chrome_skill_hooks_observe import (  # noqa: E402
    stored_messages,
    wait_completed_assistant_reply_containing,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402

_SAVE_TOOL = "skill_manage_tool"
_FAILED_STATUSES = frozenset({"error", "cancelled"})
_DONE_TOKEN = "SKILL-MANAGE-E2E-DONE"
_SKILL_DESCRIPTION = "E2E live skill manage check"

_AGENT_SYSTEM_PROMPT = (
    f"You manage the user's skills with {_SAVE_TOOL}. When the user asks you to save a skill, call "
    f"{_SAVE_TOOL} exactly once with one operation: action=save, the given name and description, and a valid "
    "SKILL.md as content (YAML frontmatter with name and description, then the body the user asks for). "
    "Never claim a skill was saved without calling the tool. "
    "After the call finishes, reply with exactly the words the user asks for."
)

# The agent's own tools reach the page asynchronously after the chat opens; a message sent before that runs
# on the default tool set, which has no skill_manage_tool.
_AGENT_TOOLS_APPLIED_JS = """((agentId, tool) => {
  const store = window.__myrmChatStore?.getState?.();
  const tools = store?.agentConfig?.enabledBuiltinTools ?? [];
  return {
    ready: store?.agentConfig?.agentId === agentId && tools.includes(tool),
    boundAgentId: store?.agentConfig?.agentId ?? null,
    tools,
  };
})"""

_OPEN_ROLLBACK_DIALOG_JS = """(() => {
  const btn = document.querySelector('[data-testid="skill-manage-rollback-button"]');
  if (!btn) return { ok: false, err: 'missing-rollback-button' };
  btn.click();
  return { ok: true };
})()"""

# What the live page holds for the turn that just ended: the store's Task Steps (the undo hint reads the batch id
# from them) and the chat's loading flag (the hint stays hidden while the last message is still loading).
_UNDO_STATE_JS = """(() => {
  const state = window.__myrmChatStore?.getState?.();
  const assistants = (state?.messages ?? []).filter((message) => message.role === 'assistant');
  const last = assistants[assistants.length - 1];
  const steps = last?.progressSteps?.length ? last.progressSteps : (last?.metadata?.progressSteps ?? []);
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  return {
    loading: state?.loading ?? null,
    assistantCount: assistants.length,
    lastAssistantId: last?.messageId ?? null,
    storeSteps: steps.map((step) => ({
      tool: step.tool_name ?? null,
      status: step.status ?? null,
      batch: step.skill_mutation_batch_id ?? null,
      error: step.error ?? null,
    })),
    hasToggle: Boolean(toggle),
    toggleExpanded: toggle?.getAttribute('data-expanded') ?? null,
    hintInDom: Boolean(document.querySelector('[data-testid="skill-manage-undo-hint"]')),
    assistantBubbles: document.querySelectorAll('[data-test-id="assistant-message"]').length,
  };
})()"""


def _user_request(name: str, marker: str) -> str:
    """One line, so the composer hands the agent exactly what was typed."""
    return (
        f"Save a new skill with {_SAVE_TOOL}: one operation, action=save, name={name}, "
        f"description={_SKILL_DESCRIPTION}. The SKILL.md content is YAML frontmatter with that name and "
        f"description, then a heading, then one body line that is exactly: {marker} . "
        f"After it is saved, reply with exactly: {_DONE_TOKEN}"
    )


def _create_agent(api_url: str, suffix: str) -> str:
    """Custom agent with only skill_manage mounted; YOLO keeps approval cards out of the turn."""
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Skill Manage Live E2E {suffix}",
            "description": "Live E2E agent that saves skills through skill_manage_tool",
            "system_prompt": _AGENT_SYSTEM_PROMPT,
            "skill_ids": [],
            "mcp_ids": [],
            "enabled_builtin_tools": ["skill_manage"],
            "security_overrides": {"yoloModeEnabled": True, "yolo_mode_enabled_at": time.time()},
        },
    )
    assert isinstance(created, dict), created
    data = created.get("data")
    agent_id = data.get("id") if isinstance(data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    return agent_id


def _create_chat(api_url: str, chat_id: str, agent_id: str) -> None:
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Skill manage live E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created


def _saved_skill_id(api_url: str, name: str) -> str | None:
    listing = http_json("GET", f"{api_url}/api/v1/skills/")
    assert isinstance(listing, dict), listing
    for skill in listing.get("skills") or []:
        if isinstance(skill, dict) and skill.get("name") == name:
            return str(skill["id"])
    return None


def _progress_steps(messages: list[dict[str, object]]) -> list[dict[str, object]]:
    """Tool steps the server persisted across the chat's messages."""
    steps: list[dict[str, object]] = []
    for message in messages:
        metadata = message.get("metadata")
        raw = message.get("progressSteps") or (metadata.get("progressSteps") if isinstance(metadata, dict) else None)
        if isinstance(raw, list):
            steps.extend(step for step in raw if isinstance(step, dict))
    return steps


def _skill_manage_batch_ids(messages: list[dict[str, object]]) -> list[str]:
    """Batch ids on the skill_manage steps the server persisted for the chat (a finished step has no status)."""
    batch_ids: list[str] = []
    for step in _progress_steps(messages):
        if not str(step.get("tool_name") or "").endswith(_SAVE_TOOL):
            continue
        batch_id = step.get("skill_mutation_batch_id")
        if step.get("status") not in _FAILED_STATUSES and isinstance(batch_id, str) and batch_id:
            batch_ids.append(batch_id)
    return batch_ids


def _describe_tool_steps(messages: list[dict[str, object]]) -> str:
    """What the agent actually did, so a failed live turn explains itself."""
    lines = [
        f"- {step.get('tool_name')} [{step.get('status')}] batch={step.get('skill_mutation_batch_id')} "
        f"{str(step.get('error') or step.get('stdout') or step.get('items') or '')[:400]}"
        for step in _progress_steps(messages)
    ]
    return "\n".join(lines) or "(no tool steps persisted)"


def _describe_undo_state(client: ChromeMcpClient, page: McpPage) -> str:
    state = client.evaluate(page, _UNDO_STATE_JS, timeout_sec=15.0)
    return f"undo state in the page: {json.dumps(state, ensure_ascii=False)}\n{describe_page(client, page)}"


def _wait_for_ui(client: ChromeMcpClient, page: McpPage, js: str, *, timeout_sec: float, chat_url: str, what: str) -> None:
    """Wait for a UI state; a miss reports what the store and the DOM held, since the page is gone at teardown."""
    try:
        state = wait_for_state(client, page, js, timeout_sec=timeout_sec, page_url=chat_url)
    except AssertionError as failure:
        pytest.fail(f"{what}: {failure}\n{_describe_undo_state(client, page)}")
    assert state.get("ready") is True, f"{what}: {state}\n{_describe_undo_state(client, page)}"


def _open_task_steps_and_rollback(client: ChromeMcpClient, page: McpPage, chat_url: str) -> None:
    """What the user does in the chat: open the undo hint, expand Task Steps, confirm the rollback."""
    _wait_for_ui(client, page, _HINT_READY_JS, timeout_sec=120.0, chat_url=chat_url, what="undo hint did not appear")
    expanded = client.evaluate(page, _STEPS_EXPANDED_JS, timeout_sec=10.0)
    if not (isinstance(expanded, dict) and expanded.get("ready") is True):
        clicked = client.evaluate(page, _CLICK_OPEN_STEPS_JS, timeout_sec=10.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked
        _wait_for_ui(client, page, _STEPS_EXPANDED_JS, timeout_sec=15.0, chat_url=chat_url, what="Task Steps did not expand")
    _wait_for_ui(client, page, _ROLLBACK_VISIBLE_JS, timeout_sec=30.0, chat_url=chat_url, what="rollback button not visible")

    opened = client.evaluate(page, _OPEN_ROLLBACK_DIALOG_JS, timeout_sec=10.0)
    assert isinstance(opened, dict) and opened.get("ok") is True, opened
    confirmed = client.evaluate(page, _CONFIRM_ROLLBACK_JS, timeout_sec=15.0)
    assert isinstance(confirmed, dict) and confirmed.get("ok") is True, confirmed
    _wait_for_ui(client, page, _TOAST_SUCCESS_JS, timeout_sec=45.0, chat_url=chat_url, what="no rollback toast")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_live_agent_saves_a_skill_and_the_user_undoes_it_from_task_steps(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    suffix = uuid.uuid4().hex[:8]
    skill_name = f"e2e-manage-{suffix}"
    marker = f"E2E_MARKER_{suffix}"
    agent_id = _create_agent(api_url, suffix)
    e2e_resource_ledger.register("agent", agent_id)
    chat_id = f"e2emanage{suffix}"
    _create_chat(api_url, chat_id, agent_id)
    e2e_resource_ledger.register("chat", chat_id)
    probe = SkillChat(
        skill_name=skill_name,
        agent_id=agent_id,
        chat_id=chat_id,
        out=tmp_path,
        log_offset=snapshot_backend_log_offset(api_url),
    )
    chat_url = f"{ui_url.rstrip('/')}{probe.ui_path}"

    def agent_tools_applied(client: ChromeMcpClient, page: McpPage) -> None:
        probe_js = f"({_AGENT_TOOLS_APPLIED_JS})({json.dumps(agent_id)}, {json.dumps('skill_manage')})"
        applied = wait_for_state(client, page, probe_js, timeout_sec=90.0, page_url=chat_url)
        assert applied.get("ready") is True, applied

    def after_send(client: ChromeMcpClient, page: McpPage) -> None:
        try:
            wait_completed_assistant_reply_containing(chat_id, api_url, _DONE_TOKEN, timeout_sec=180.0)
        except pytest.fail.Exception as failure:
            pytest.fail(f"{failure}\n{describe_page(client, page)}")

        stored = stored_messages(chat_id, api_url)
        batch_ids = _skill_manage_batch_ids(stored)
        assert batch_ids, (
            f"no {_SAVE_TOOL} step with a batch id was persisted; the agent did:\n"
            f"{_describe_tool_steps(stored)}\n{describe_page(client, page)}"
        )
        skill_id = _saved_skill_id(api_url, skill_name)
        assert skill_id, f"skill {skill_name!r} is not in the catalog after the live turn"
        saved_md = _fetch_skill_md(api_url, quote(skill_id, safe=""))
        assert marker in saved_md, f"the saved SKILL.md lost the marker the user asked for:\n{saved_md[:600]}"
        print(f"E2E_SKILL_SAVED: id={skill_id} batches={json.dumps(batch_ids)}", flush=True)

        _open_task_steps_and_rollback(client, page, chat_url)

        deadline = time.monotonic() + 90.0
        while _saved_skill_id(api_url, skill_name) is not None:
            assert time.monotonic() < deadline, f"skill {skill_name!r} survived the confirmed rollback"
            time.sleep(1.0)

    # The private backend and its log are reaped at teardown, so a failed turn has to print its own server evidence.
    with dump_backend_log_on_failure(api_url):
        drive_chat_turn(
            ui_url,
            probe,
            _user_request(skill_name, marker),
            invoke_skill=False,
            before_send=agent_tools_applied,
            while_open=after_send,
        )
