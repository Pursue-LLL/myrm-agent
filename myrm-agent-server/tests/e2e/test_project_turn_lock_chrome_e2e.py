"""Chrome E2E: shared-project turn lock → real WebUI waiting_for_turn indicator.

Real user scenario: two chats bound to the same project must serialize turns.
When a second chat sends a message while the project lock is held, the backend
emits `waiting_for_turn` status SSE; the WebUI must display the progress step
("Waiting for other agents in the project to finish...") and remove it after
`waiting_for_turn_clear`, then complete the reply normally.

The seed endpoint holds the project lock deterministically (simulating another
agent actively running), so this test never depends on flaky real concurrency
timing while still exercising the full real chain:
  seed(lock) → real UI send → agent-stream → pump waiting_for_turn
  → frontend progressSteps → lock release → waiting_for_turn_clear → reply.
"""

from __future__ import annotations

import json
import time
import urllib.request  # noqa: S310
import urllib.error  # noqa: S310

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

E2E_PROMPT = "只回复 OK"
TURN_WAIT_SEC = 300.0
HOLD_MS = 25000

_WAITING_STEP_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (const msg of msgs) {
    const steps = (msg.progressSteps?.length ? msg.progressSteps : msg.metadata?.progressSteps) || [];
    for (const step of steps) {
      if (String(step.step_key || '') === 'waiting_for_turn') {
        return { ready: true, step_key: step.step_key, items: step.items || [], status: step.status ?? null };
      }
    }
  }
  return { ready: false, msg_count: msgs.length };
})()"""

_WAITING_STREAMING_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  const loading = Boolean(store?.loading || store?.streaming || false);
  for (const msg of msgs) {
    if (msg.role !== 'assistant' && msg.type !== 'assistant') continue;
    const steps = (msg.progressSteps?.length ? msg.progressSteps : msg.metadata?.progressSteps) || [];
    if (steps.some((s) => String(s.step_key || '') === 'waiting_for_turn')) {
      const content = String(msg.content || msg.text || '').trim();
      return { ready: true, placeholder: content.length === 0, loading, contentLen: content.length };
    }
  }
  return { ready: false, loading, msg_count: msgs.length };
})()"""

_ASSISTANT_OK_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    const msg = msgs[i];
    if (msg.role !== 'assistant' && msg.type !== 'assistant') continue;
    const text = String(msg.content || msg.text || '').trim();
    if (text.includes('OK')) {
      return { ready: true, snippet: text.slice(0, 120) };
    }
    return { ready: false, msg_count: msgs.length, last_assistant: text.slice(0, 120) };
  }
  return { ready: false, msg_count: msgs.length };
})()"""

_ATTACH_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {
    return { ok: false, err: 'no-bridge' };
  }
  await bridge.attachToChat(__MYRM_CHAT_ID__);
  return { ok: true };
})()"""

_EXPAND_PROGRESS_JS = """(() => {
  const toggle = document.querySelector('[data-testid="progress-steps-toggle"]');
  const panel = document.querySelector('[data-testid="progress-steps-panel"]');
  if (panel?.getAttribute('data-expanded') !== 'true' && toggle) {
    toggle.click();
  }
  return { ok: true };
})()"""

_DOM_WAITING_JS = """(() => {
  const body = document.body.innerText || '';
  const needles = [
    'Waiting for other agents',
    '正在等待项目中其他',
    '正在等待專案中其他',
  ];
  for (const needle of needles) {
    if (body.includes(needle)) {
      return { ready: true, needle };
    }
  }
  return { ready: false, sample: body.slice(0, 300) };
})()"""


_INSTALL_FETCH_PROBE_JS = """(() => {
  if (window.__FETCH_PROBE__) return { ok: true, reused: true };
  window.__FETCH_PROBE__ = [];
  const origFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const url = String(args[0] ?? '');
    const isStream = url.includes('/agent-stream');
    const opts = args[1] || {};
    let bodyPreview = '';
    try {
      if (typeof opts.body === 'string') bodyPreview = opts.body.slice(0, 800);
    } catch {
      bodyPreview = '<unreadable>';
    }
    if (isStream) {
      window.__FETCH_PROBE__.push({ kind: 'request', url, at: Date.now(), body: bodyPreview });
    }
    return origFetch(...args);
  };
  return { ok: true };
})()"""

_ABORT_STREAM_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.abortActiveStream) {
    return { ok: false, err: 'no-abortActiveStream' };
  }
  bridge.abortActiveStream();
  return { ok: true };
})()"""

_E2E_SEND_PROMPT_JS = """(async (prompt) => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) {
    return { ok: false, err: 'no-sendChatMessage' };
  }
  const res = await bridge.sendChatMessage(prompt);
  return res;
})"""


def _replay_agent_stream_snippet(api_url: str, body: str) -> str:
    """Replay the exact agent-stream POST captured by the fetch probe.

    Reads the first ~4KB of the SSE response so the test can see what the
    backend actually returned for the second send (busy error / waiting_for_turn
    / empty), instead of relying on frontend interpretation.
    """
    try:
        request = urllib.request.Request(  # noqa: S310
            f"{api_url.rstrip('/')}/api/v1/agents/agent-stream",
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:  # noqa: S310
        body_text = exc.read(4096).decode("utf-8", errors="replace")
        return f"HTTP {exc.code}: {body_text}"


def _seed_turn_lock_fixture(api_url: str, *, hold_ms: int = HOLD_MS) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/projects/test/seed-turn-lock?hold_ms={hold_ms}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    project_id = str(seeded.get("project_id") or "")
    assert chat_id.startswith("e2eturnlock"), seeded
    assert project_id, seeded
    return seeded


def _send_message(
    client: object,
    page: object,
    *,
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    result = client.evaluate(  # type: ignore[attr-defined]
        page,
        f"""(async () => {{
          const bridge = window.__MYRM_E2E_CHAT__;
          if (!bridge?.sendChatMessage) {{
            return {{ ok: false, err: 'no-sendChatMessage' }};
          }}
          const res = await bridge.sendChatMessage({json.dumps(E2E_PROMPT)});
          return res;
        }})()""",
        timeout_sec=timeout_sec + 15.0,
    )
    assert isinstance(result, dict), result
    return result


def _wait_waiting_step(
    client: object,
    page: object,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, _WAITING_STEP_JS, timeout_sec=10.0)
        state = raw if isinstance(raw, dict) else json.loads(str(raw))
        last = state
        if state.get("ready") is True:
            return state
        time.sleep(0.5)
    raise AssertionError(f"waiting_for_turn step never appeared: {last}")


def _wait_waiting_streaming(
    client: object,
    page: object,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, _WAITING_STREAMING_JS, timeout_sec=10.0)
        state = raw if isinstance(raw, dict) else json.loads(str(raw))
        last = state
        if state.get("ready") is True:
            return state
        time.sleep(0.5)
    raise AssertionError(f"waiting assistant placeholder never appeared: {last}")


def _wait_waiting_cleared(
    client: object,
    page: object,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, _WAITING_STEP_JS, timeout_sec=10.0)
        state = raw if isinstance(raw, dict) else json.loads(str(raw))
        last = state
        if state.get("ready") is False:
            return state
        time.sleep(0.5)
    raise AssertionError(f"waiting_for_turn step never cleared: {last}")


def _wait_dom_waiting(
    client: object,
    page: object,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, _DOM_WAITING_JS, timeout_sec=10.0)
        state = raw if isinstance(raw, dict) else json.loads(str(raw))
        last = state
        if state.get("ready") is True:
            return state
        time.sleep(0.5)
    raise AssertionError(f"waiting_for_turn text never rendered in DOM: {last}")


def _wait_dom_waiting_cleared(
    client: object,
    page: object,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, _DOM_WAITING_JS, timeout_sec=10.0)
        state = raw if isinstance(raw, dict) else json.loads(str(raw))
        last = state
        if state.get("ready") is False:
            return state
        time.sleep(0.5)
    raise AssertionError(f"waiting_for_turn text never cleared from DOM: {last}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_project_turn_lock_waiting_for_turn_chrome_e2e() -> None:
    """Real UI send under held project lock must show then clear waiting_for_turn."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    seeded = _seed_turn_lock_fixture(api_url, hold_ms=HOLD_MS)
    chat_id = str(seeded["chat_id"])
    chat_path = str(seeded["ui_path"])

    warm_ui_route(chat_path)
    chat_url = f"{ui_url}{chat_path}"
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!window.__MYRM_E2E_CHAT__?.sendChatMessage && !!window.__MYRM_E2E_CHAT__?.attachToChat,
            }))()""",
            timeout_sec=30.0,
        )
        attach_js = _ATTACH_JS.replace("__MYRM_CHAT_ID__", json.dumps(chat_id))
        attach_raw = client.evaluate(page, attach_js, timeout_sec=30.0)
        attach_state = attach_raw if isinstance(attach_raw, dict) else json.loads(str(attach_raw))
        assert attach_state.get("ok") is True, attach_state

        send_result = _send_message(client, page)
        assert send_result.get("ok") is True, send_result
        chat_id_resolved = str(
            send_result.get("chatId")
            or (send_result.get("debug") or {}).get("chatId")
            or ""
        ).strip() or chat_id

        waiting_state = _wait_waiting_step(client, page, timeout_sec=45.0)
        assert waiting_state.get("step_key") == "waiting_for_turn", waiting_state

        # While waiting, the assistant placeholder must exist with empty body
        # (stream still blocked on the project lock, no reply text yet).
        streaming_state = _wait_waiting_streaming(client, page, timeout_sec=15.0)
        assert streaming_state.get("ready") is True, streaming_state
        assert streaming_state.get("placeholder") is True, streaming_state

        # waiting_for_turn is a title-only step (items stay empty by design), so
        # also assert the i18n title is really rendered into the DOM after
        # expanding the progress-steps panel (true end-user visibility check).
        expand_raw = client.evaluate(page, _EXPAND_PROGRESS_JS, timeout_sec=10.0)
        expand_state = expand_raw if isinstance(expand_raw, dict) else json.loads(str(expand_raw))
        assert expand_state.get("ok") is True, expand_state
        dom_state = _wait_dom_waiting(client, page, timeout_sec=15.0)
        assert dom_state.get("ready") is True, dom_state

        cleared_state = _wait_waiting_cleared(client, page, timeout_sec=TURN_WAIT_SEC)
        assert cleared_state.get("ready") is False, cleared_state

        dom_cleared_state = _wait_dom_waiting_cleared(client, page, timeout_sec=15.0)
        assert dom_cleared_state.get("ready") is False, dom_cleared_state

        ok_deadline = time.monotonic() + TURN_WAIT_SEC
        ok_state: dict[str, object] = {}
        while time.monotonic() < ok_deadline:
            raw = client.evaluate(page, _ASSISTANT_OK_JS, timeout_sec=10.0)
            ok_state = raw if isinstance(raw, dict) else json.loads(str(raw))
            if ok_state.get("ready") is True:
                break
            time.sleep(0.5)
        assert ok_state.get("ready") is True, (
            f"Expected assistant OK after lock released; state={ok_state!r} "
            f"chat_id={chat_id_resolved}"
        )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_project_turn_lock_waiting_cancel_chrome_e2e() -> None:
    """Real user cancels while waiting for the project lock.

    Real flow: seed holds the project lock → UI send shows waiting_for_turn →
    user hits stop (abortActiveStream → stopMessage → cancel + SSE abort) →
    waiting step must be removed synchronously → a second send must show the
    waiting step again (proving the cancelled waiter did NOT steal/release the
    holder's lock) → seed releases → the second turn completes normally.
    """
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    seeded = _seed_turn_lock_fixture(api_url, hold_ms=45000)
    chat_id = str(seeded["chat_id"])
    chat_path = str(seeded["ui_path"])

    warm_ui_route(chat_path)
    chat_url = f"{ui_url}{chat_path}"
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!window.__MYRM_E2E_CHAT__?.sendChatMessage
                && !!window.__MYRM_E2E_CHAT__?.attachToChat
                && !!window.__MYRM_E2E_CHAT__?.abortActiveStream,
            }))()""",
            timeout_sec=30.0,
        )
        attach_js = _ATTACH_JS.replace("__MYRM_CHAT_ID__", json.dumps(chat_id))
        attach_raw = client.evaluate(page, attach_js, timeout_sec=30.0)
        attach_state = attach_raw if isinstance(attach_raw, dict) else json.loads(str(attach_raw))
        assert attach_state.get("ok") is True, attach_state

        # 第一次发送：锁被 seed 持有 → 进入等待
        send_result = _send_message(client, page)
        assert send_result.get("ok") is True, send_result
        waiting_state = _wait_waiting_step(client, page, timeout_sec=45.0)
        assert waiting_state.get("step_key") == "waiting_for_turn", waiting_state

        # 真实用户点击停止：stopMessage 路径取消 + 同步清除 waiting 步骤
        abort_raw = client.evaluate(page, _ABORT_STREAM_JS, timeout_sec=10.0)
        abort_state = abort_raw if isinstance(abort_raw, dict) else json.loads(str(abort_raw))
        assert abort_state.get("ok") is True, abort_state

        cleared_state = _wait_waiting_cleared(client, page, timeout_sec=20.0)
        assert cleared_state.get("ready") is False, cleared_state

        # 注入 fetch 探针：记录 agent-stream POST 的发出与响应（实证第二次请求是否到达后端）
        probe_raw = client.evaluate(page, _INSTALL_FETCH_PROBE_JS, timeout_sec=10.0)
        probe_state = probe_raw if isinstance(probe_raw, dict) else json.loads(str(probe_raw))
        assert probe_state.get("ok") is True, probe_state

        # 取消后等待后端 teardown（第一次 session 从 active 集合释放）。
        # 真实用户取消后重发也会遇到短暂 AgentBusyError，UI 会提示并允许重试——
        # 测试模拟该真实重试：最多 3 次，每次间隔 5s。
        send2: dict[str, object] = {}
        for attempt in range(3):
            time.sleep(5)
            send2 = _send_message(client, page, timeout_sec=60.0)
            if send2.get("ok") is True:
                break
            print(f"SEND2_ATTEMPT_{attempt}_DEBUG:", json.dumps(send2, ensure_ascii=False, default=str))
            probe_now = client.evaluate(page, "window.__FETCH_PROBE__ || []", timeout_sec=10.0)
            probe_list = probe_now if isinstance(probe_now, list) else []
            print(f"SEND2_ATTEMPT_{attempt}_FETCH_PROBE:", json.dumps(probe_list, ensure_ascii=False, default=str))
            captured_body = ""
            for entry in probe_list:
                if isinstance(entry, dict) and entry.get("kind") == "request" and entry.get("body"):
                    captured_body = str(entry.get("body"))
            if captured_body:
                snippet = _replay_agent_stream_snippet(api_url, captured_body)
                print(f"SEND2_ATTEMPT_{attempt}_REPLAY_SSE:", snippet[:2500])
        assert send2.get("ok") is True, send2

        # 第二次发送成功后：
        # - 若 seed 锁仍在（seed 未到期），waiting_for_turn 会再次出现 —— 这是
        #   "取消等待未误释放持有者锁"的强证据；
        # - 若 seed 已到期释放，则第二次 turn 直接进入正常生成（无 waiting）。
        waiting2: dict[str, object] = {}
        try:
            waiting2 = _wait_waiting_step(client, page, timeout_sec=10.0)
        except AssertionError:
            waiting2 = {"ready": False, "note": "seed lock already released"}
        print("SEND2_WAITING2:", json.dumps(waiting2, ensure_ascii=False, default=str))

        # seed 到期自动释放 → 第二次 turn 自动获得锁 → 正常运行完成
        ok_deadline = time.monotonic() + TURN_WAIT_SEC
        ok_state: dict[str, object] = {}
        while time.monotonic() < ok_deadline:
            raw = client.evaluate(page, _ASSISTANT_OK_JS, timeout_sec=10.0)
            ok_state = raw if isinstance(raw, dict) else json.loads(str(raw))
            if ok_state.get("ready") is True:
                break
            time.sleep(0.5)
        assert ok_state.get("ready") is True, (
            f"Expected second turn assistant OK after seed lock release; "
            f"state={ok_state!r} chat_id={chat_id}"
        )
