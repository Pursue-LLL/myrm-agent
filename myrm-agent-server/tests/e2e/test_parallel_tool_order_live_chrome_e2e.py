"""Chrome LIVE_AGENT E2E: four conflicting tool calls of one real model message run one at a time, in the order the
user listed them, whether the run is auto-approved or parked behind the user's approval.

The user types four shell steps into the composer and asks for them in one step. Each step records when it started and
ended in a log the steps share, so the log shows what really ran: the order and that no two overlapped. The chat's usage
ledger (one row per model call, with the reason the call ended) shows whether two calls came from one model message: no
model call that ended by asking for tools falls between their starts. With approval on, the calls only start once the
user pressed Approve in the card(s) the run parked behind, and the run that executes them is resumed from the stored
state.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_parallel_tool_order_live_chrome_e2e.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from e2e_core.dev_ports import shared_ui_base

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    e2e_runtime_bootstrap_apply_js,
    ensure_e2e_yolo_mode,
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.api.agent.utils import _strip_provider_prefix, get_lite_model_selection  # noqa: E402
from tests.support.chrome_mcp_e2e import get_e2e_ui_url, http_json, open_mcp_page  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402
from tests.support.hitl_live_e2e import pin_private_hitl_mode  # noqa: E402
from tests.support.tool_order_probe import (  # noqa: E402
    BASH_STEP_KEY,
    LEDGER_NAME,
    STEP_LOG_NAME,
    TAGS,
    Step,
    bash_tags_in,
    ran_in_one_message,
    read_steps,
    step_script,
    tool_round_ends_ns,
)

BASE_URL = os.getenv("E2E_UI_BASE", shared_ui_base()).rstrip("/")

_DONE_MARKER = "ORDER_LIVE_OK"
_MAX_TURN_ATTEMPTS = 3
_TURN_TIMEOUT_SEC = 240.0
# Another attempt only starts when a whole turn still fits in the test's own timeout.
_TEST_BUDGET_SEC = 540.0
_APPROVAL_CLICK_BUDGET = 8
_STORED_STEPS_TIMEOUT_SEC = 60.0

_PIN_LITE_MODEL_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) {
    return { ok: false, err: 'no-pinLiteModelForE2e' };
  }
  return bridge.pinLiteModelForE2e().then((pinned) => ({ ok: true, pinned }));
})()"""

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return { ready: !!bridge?.handleSubmit && !!debug.selection, selection: debug.selection ?? null };
})()"""

_ENSURE_CHAT_SESSION_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.ensureChatSession) return { ok: false, err: 'no ensureChatSession' };
  return bridge.ensureChatSession().then(() => ({ ok: true }));
})()"""

_TURN_STATE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {};
  const approvals = bridge?.toolApprovalSnapshot?.() ?? {};
  return {
    isStreaming: Boolean(snap.isStreaming),
    userCount: snap.userCount ?? 0,
    sample: String(snap.lastAssistantSample || '').slice(0, 300),
    queueLen: Number(approvals.queueLen ?? 0),
  };
})()"""

# Several parked calls share one dialog with an Approve All button; a lone call has its own Approve button. Matching the
# whole label keeps the press off buttons that only mention approval.
_CLICK_APPROVE_JS = """(() => {
  const enabled = Array.from(document.querySelectorAll('button')).filter((btn) => !btn.disabled);
  const labelled = (pattern) => enabled.find((btn) => pattern.test((btn.textContent || '').trim()));
  const approve = labelled(/^(Approve All|全部批准)$/) ?? labelled(/^(Approve|批准)$/);
  if (!approve) return { ok: false, err: 'approve-button-not-found' };
  approve.scrollIntoView({ block: 'center' });
  approve.click();
  return { ok: true, label: (approve.textContent || '').trim() };
})()"""


def _trace(stage: str, detail: str) -> None:
    print(f"E2E_ORDER_{stage}: {detail}", flush=True)


@dataclass(frozen=True)
class Turn:
    """What one real turn left behind: the log's steps, the bash steps the chat stored, the Approve presses and the
    ends of the model calls that asked for tools."""

    steps: list[Step]
    stored_tags: list[str]
    approvals: int
    tool_round_ends_ns: list[int]


def _create_agent(api_url: str, *, yolo: bool) -> str:
    payload = {
        "name": f"Parallel order LIVE {uuid.uuid4().hex[:8]}",
        "description": "Chrome LIVE E2E for the start order of conflicting tool calls",
        "system_prompt": (
            f"You run shell commands with {BASH_STEP_KEY}. The tool runs the calls of one response one after another, "
            "in the order you list them. When the user lists several commands, make one call per command, all in the "
            "same response and in the order listed; never wait for one result before the next call and never combine "
            "commands into one call. After the results arrive, reply with the text the user asked for."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
        "security_overrides": {"yoloModeEnabled": True, "yolo_mode_enabled_at": time.time()} if yolo else {},
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict), created
    data = created.get("data")
    agent_id = data.get("id") if isinstance(data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    return agent_id


def _user_prompt(script: Path) -> str:
    commands = "\n".join(f"{number}. python3 {script} {tag}" for number, tag in enumerate(TAGS, start=1))
    return (
        f"Run these four shell commands, each as its own call of {BASH_STEP_KEY}, all four in your next response "
        f"(the tool runs them one after another in the order you list them):\n{commands}\n"
        f"When they have finished, reply with exactly: {_DONE_MARKER}"
    )


async def _wait_stored_bash_tags(chat_id: str, *, api_url: str) -> list[str]:
    """The chat stores its steps when the turn ends, a moment after the page stops streaming."""
    deadline = time.monotonic() + _STORED_STEPS_TIMEOUT_SEC
    tags = bash_tags_in(fetch_chat_messages(chat_id, api_url=api_url))
    while len(tags) < len(TAGS) and time.monotonic() < deadline:
        heartbeat_once()
        await asyncio.sleep(2.0)
        tags = bash_tags_in(fetch_chat_messages(chat_id, api_url=api_url))
    return tags


async def _drive_turn(chat: McpChatSession, log: Path, *, approval: bool) -> int:
    """Wait for the four steps to have run and the page to stop streaming; with approval on, press Approve as a user would.

    Returns how many times Approve was pressed.
    """
    deadline = time.monotonic() + _TURN_TIMEOUT_SEC
    clicks = 0
    state: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_once()
        raw = await chat.evaluate(_TURN_STATE_JS, intent=EvaluateIntent.BRIDGE_POLL)
        state = raw if isinstance(raw, dict) else {"value": raw}
        if approval and int(state.get("queueLen") or 0) > 0:
            clicked = await chat.evaluate(_CLICK_APPROVE_JS, intent=EvaluateIntent.AGENT_SUBMIT)
            if isinstance(clicked, dict) and clicked.get("ok") is True:
                clicks += 1
                assert clicks <= _APPROVAL_CLICK_BUDGET, f"more approval presses than expected: {state}"
                _trace("approve", f"n={clicks} queue={state.get('queueLen')} label={clicked.get('label')!r}")
                await asyncio.sleep(1.0)
                continue
        finished = len(read_steps(log)) >= len(TAGS) and state.get("isStreaming") is False
        if finished and int(state.get("userCount") or 0) >= 1:
            return clicks
        await asyncio.sleep(1.5)
    raise AssertionError(
        f"turn did not finish within {_TURN_TIMEOUT_SEC}s: state={state}; approvals={clicks}; "
        f"log={log.read_text(encoding='utf-8') if log.exists() else '<missing>'!r}"
    )


async def _run_turn(chat: McpChatSession, api_base: str, ledger: E2EResourceLedger, *, approval: bool) -> Turn:
    """One real turn in a new chat."""
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    ensured = await chat.evaluate(_ENSURE_CHAT_SESSION_JS, intent=EvaluateIntent.ROUTE_ATTACH)
    assert isinstance(ensured, dict) and ensured.get("ok") is True, ensured

    chat_id = str((await chat.bridge_chat_id()) or "").strip()
    assert chat_id, "expected a client chat id after opening a new chat"
    seeded = http_json("POST", f"{api_base}/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}")
    assert isinstance(seeded, dict) and str(seeded.get("chat_id")) == chat_id, seeded
    workspace = Path(str(seeded["file_path"])).parent
    script = workspace / "step.py"
    script.write_text(step_script(), encoding="utf-8")
    log = workspace / STEP_LOG_NAME
    assert not log.exists(), f"the log must not exist before the turn: {log}"

    prompt = _user_prompt(script)
    sent = await chat.send_message(prompt, prompt)
    chat_id_hint = str(sent.get("started", {}).get("chatId") or sent.get("submit", {}).get("chatId") or chat_id).strip()
    heartbeat_once()
    started = await chat.wait_stream_started(prompt, timeout_sec=120.0, chat_id_hint=chat_id_hint or None)
    resolved = chat_id_hint or str(started.get("chatId") or "").strip()
    assert resolved, f"expected a chat id once the stream started: started={started}; send={sent}"
    ledger.register("chat", resolved)
    _trace("sent", f"chat={resolved} approval={approval}")

    # The page stays where the user typed: reloading it would run the shared modal-dismissal helper, which presses
    # Reject All on an approval dialog the run is parked behind.
    approvals = await _drive_turn(chat, log, approval=approval)
    turn = Turn(
        steps=read_steps(log),
        stored_tags=await _wait_stored_bash_tags(resolved, api_url=api_base),
        approvals=approvals,
        tool_round_ends_ns=tool_round_ends_ns(workspace / LEDGER_NAME),
    )
    _trace("turn_done", repr(turn))
    return turn


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
@pytest.mark.parametrize("approval", [True, False], ids=["after_user_approval", "auto_approved"])
async def test_conflicting_calls_of_one_message_start_in_the_users_order_live(
    e2e_resource_ledger: E2EResourceLedger, approval: bool
) -> None:
    test_started = time.monotonic()
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for the live E2E — run via ./myrm-dev test -m chrome_e2e after ./myrm-dev ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    if approval:
        pin_private_hitl_mode(api_base)
    else:
        ensure_e2e_yolo_mode(api_url=api_base)
    agent_id = _create_agent(api_base, yolo=not approval)
    e2e_resource_ledger.register("agent", agent_id)

    async def apply_bootstrap(chat: McpChatSession) -> None:
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        if not bootstrap_js:
            await chat.ensure_e2e_api_base_binding()
            return
        result = await chat.evaluate(bootstrap_js, intent=EvaluateIntent.AGENT_SUBMIT)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(f"E2E runtime bootstrap failed: {result}")

    async def wait_agent_applied(chat: McpChatSession) -> None:
        deadline = time.monotonic() + 90.0
        last: object = None
        while time.monotonic() < deadline:
            heartbeat_once()
            last = await chat.evaluate(_AGENT_READY_JS, intent=EvaluateIntent.BRIDGE_POLL)
            if isinstance(last, dict) and last.get("ready") is True:
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"E2E chat bridge not ready after loading the agent: {last}")

    async def pin_lite_model(chat: McpChatSession) -> None:
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        pinned = await chat.evaluate(_PIN_LITE_MODEL_JS, intent=EvaluateIntent.AGENT_SUBMIT)
        assert isinstance(pinned, dict) and pinned.get("ok") is True, f"Failed to pin the lite model: {pinned}"
        expected = get_lite_model_selection()
        model = pinned.get("pinned")
        assert isinstance(model, dict), f"Missing pinned model payload: {pinned}"
        assert model.get("providerId") == expected["providerId"]
        assert model.get("model") == _strip_provider_prefix(str(expected["model"]))

    agent_url = f"{ui_base}/?agentId={agent_id}"
    outcomes: list[str] = []
    batched = False
    with open_mcp_page(agent_url, timeout_ms=120_000) as (client, page):
        chat = McpChatSession(client, page)
        await chat.bootstrap(agent_url, timeout_sec=180.0)
        await apply_bootstrap(chat)
        await chat.dismiss_modals()
        await wait_agent_applied(chat)
        await pin_lite_model(chat)
        _trace("ready", f"agent={agent_id} approval={approval}")

        for attempt in range(1, _MAX_TURN_ATTEMPTS + 1):
            turn = await _run_turn(chat, api_base, e2e_resource_ledger, approval=approval)
            steps = turn.steps
            # What the log shows holds however the model split its calls over messages: one at a time, in listed order.
            assert [step.tag for step in steps] == list(TAGS), f"steps ran as {steps}, expected {list(TAGS)}"
            assert all(earlier.ended_ns <= later.started_ns for earlier, later in zip(steps, steps[1:], strict=False)), steps
            assert turn.stored_tags == list(TAGS), f"the chat stored the bash steps as {turn.stored_tags}, expected {list(TAGS)}"
            assert (turn.approvals > 0) == approval, f"approvals pressed: {turn.approvals}; approval mode: {approval}"
            if ran_in_one_message(steps, turn.tool_round_ends_ns):
                batched = True
                break
            outcomes.append(f"attempt {attempt}: {turn}")
            if time.monotonic() - test_started + _TURN_TIMEOUT_SEC > _TEST_BUDGET_SEC:
                break

    assert batched, f"the model never issued two of the calls as one message, so none were conflicting at once: {outcomes}"
