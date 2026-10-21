"""Chrome E2E: a real turn still works while the OS asks for reduced motion.

Prerequisites:
  ./myrm ready --attach --chrome   (needs BASIC_API_KEY / BASIC_MODEL in .env.test)

This is the user-facing scenario the guards could plausibly break: a person with "reduce motion"
turned on sends a real prompt and must still get a real model reply, with the streamed answer
rendering into the chat. It uses the live model (no mocks) and keeps the preference emulated for
the whole turn.

Covers:
  T1 - The page runs under prefers-reduced-motion:reduce while the turn is sent.
  T2 - The decorative animations are collapsed in that state (the guard is active, not a no-op).
  T3 - A real model reply arrives and the assistant bubble renders it.

Uses a self-created CDP target: Chrome allows one client per target and the orchestrator already
owns the page it opens, so a second connection would displace that session.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

import pytest


def _cdp_base() -> str:
    """The E2E Chrome port is dynamic per run; the harness exports it as MYRM_CHROME_E2E_PORT."""
    return f"http://127.0.0.1:{os.environ.get('MYRM_CHROME_E2E_PORT', '9333')}"


def _ui_url() -> str:
    """LIVE/PRIVATE runs bind their own UI port; E2E_UI_BASE is the SSOT for it."""
    return os.environ.get("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/") + "/"


_PROBE_JS = """(() => {
  const nodes = Array.from(document.querySelectorAll('.animate-pulse'));
  const node = nodes.find((n) => getComputedStyle(n).animationName !== 'none');
  return {
    found: Boolean(node),
    duration: node ? getComputedStyle(node).animationDuration : null,
    iterations: node ? getComputedStyle(node).animationIterationCount : null,
    reduced: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    bridge: typeof window.__MYRM_E2E_CHAT__?.sendChatMessage === 'function',
  };
})()"""

_SEND_JS = """(async () => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, err: 'no-sendChatMessage' };
  bridge.setActionMode?.('agent');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage('Reply with exactly: REDUCED-OK', {
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  });
  return { ...result, usersBefore };
})()"""

_REPLY_JS = """(() => {
  const snapshot = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const sample = String(snapshot.lastAssistantSample || '');
  return {
    isStreaming: snapshot.isStreaming === true,
    sample: sample.slice(0, 400),
    hasReply: !snapshot.isStreaming && sample.trim().length > 0,
  };
})()"""


class _Target:
    """One raw CDP target with a tiny command helper."""

    def __init__(self) -> None:
        from e2e_core.effect_guard import assert_http_effect_allowed

        _new_target_url = f"{_cdp_base()}/json/new?about:blank"
        assert_http_effect_allowed(method="PUT", url=_new_target_url)
        request = urllib.request.Request(_new_target_url, method="PUT")
        self._info = json.load(urllib.request.urlopen(request, timeout=15))
        from websockets.sync.client import connect

        self._ws = connect(self._info["webSocketDebuggerUrl"], open_timeout=15, close_timeout=5, max_size=None)
        self._seq = 0

    def send(self, method: str, params: dict | None = None, timeout: float = 60.0) -> dict:
        self._seq += 1
        message_id = self._seq
        self._ws.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self._ws.recv(timeout=timeout))
            if message.get("id") == message_id:
                return message

    def js(self, expression: str, timeout: float = 60.0) -> object:
        result = self.send(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            timeout=timeout,
        )
        payload = result.get("result", {})
        if payload.get("exceptionDetails"):
            raise AssertionError(f"page raised: {payload['exceptionDetails']}")
        return payload.get("result", {}).get("value")

    def wait_until(self, expression: str, *, timeout_sec: float, description: str) -> dict:
        deadline = time.monotonic() + timeout_sec
        last: dict = {}
        while time.monotonic() < deadline:
            value = self.js(expression)
            if isinstance(value, dict):
                last = value
                if last.get("found") and last.get("bridge"):
                    return last
                if last.get("hasReply"):
                    return last
            time.sleep(1.0)
        raise AssertionError(f"{description} did not happen within {timeout_sec}s; last={last!r}")

    def close(self) -> None:
        try:
            self._ws.close()
        finally:
            try:
                urllib.request.urlopen(f"{_cdp_base()}/json/close/{self._info['id']}", timeout=5)
            except OSError:
                pass


def _seconds(value: str) -> float:
    """Computed durations arrive as `2s`, `1e-05s` or `0.01ms`."""
    text = str(value).strip()
    if text.endswith("ms"):
        return float(text[:-2]) / 1000.0
    if text.endswith("s"):
        return float(text[:-1])
    raise AssertionError(f"unexpected computed duration: {value!r}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="LIVE",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_real_turn_completes_under_reduced_motion() -> None:
    """A person with reduce-motion on must still get a real model answer."""
    from tests.support.chrome_mcp_e2e import get_e2e_api_url, wait_e2e_provider_ready
    from tests.support.e2e_provider_seed import seed_live_e2e_providers

    # A live turn needs a provider in the WebUI config, exactly as a real person sets up.
    api_url = get_e2e_api_url()
    seed_live_e2e_providers(api_url)
    assert wait_e2e_provider_ready(timeout_sec=90.0), "provider never became ready for the live turn"

    target = _Target()
    try:
        target.send("Page.enable")
        target.send(
            "Emulation.setEmulatedMedia",
            {"features": [{"name": "prefers-reduced-motion", "value": "reduce"}]},
        )
        target.send("Page.navigate", {"url": _ui_url()})

        # T1 + T2: ready under reduce, with the guard actually collapsing the loop.
        state = target.wait_until(_PROBE_JS, timeout_sec=180.0, description="chat bridge + pulse ready under reduce")
        assert state["reduced"] is True, f"reduce did not reach the page: {state!r}"
        assert _seconds(state["duration"]) <= 0.001, f"guard inactive: {state!r}"
        assert state["iterations"] == "1", f"guard inactive: {state!r}"

        # T3: send a real prompt and wait for the real model reply.
        #
        # `sendChatMessage` can report ok:false with `send-kickoff-no-progress` when the turn
        # snapshot has not registered the user row yet (`userCount: 0`) even though the assistant
        # reply does arrive. The user-visible outcome is the reply itself, so that is what this
        # asserts; the bridge diagnostic is kept in the failure message for triage.
        sent = target.js(_SEND_JS, timeout=120.0)
        assert isinstance(sent, dict), f"send returned nothing usable: {sent!r}"

        reply = target.wait_until(_REPLY_JS, timeout_sec=240.0, description="assistant reply for the live turn")
        assert reply["hasReply"] is True, (
            f"no assistant reply rendered; send={json.dumps(sent, ensure_ascii=False)[:600]}; probe={reply!r}"
        )
        assert reply["sample"].strip(), f"assistant reply was empty: {reply!r}"
    finally:
        target.close()
