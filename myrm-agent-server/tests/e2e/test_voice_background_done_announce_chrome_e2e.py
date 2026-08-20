"""Chrome E2E for #3 VoiceBackgroundCompletionDuplexAnnounce.

Covers the real WebUI announcement path: a completed voice background task
reaches the browser over the real SSE notification stream, and the frontend
`useGlobalEvents` handler dispatches the `voice-bg-done` CustomEvent that
`VoiceSessionButton` consumes to announce completion over TTS.

Flow (no mocks on the delivery path):
  1. Open the WebUI /agents route so the global SSE listener is mounted.
  2. Seed a completed voice background task via the local-only fixture
     endpoint (`POST /background-tasks/test/seed-voice-done`), which builds a
     voice Kanban task and publishes BACKGROUND_TASK_DONE through the real
     Kanban event publisher.
  3. The running WebuiVoiceWorkNotifier appends the result message to the
     chat and broadcasts SYSTEM_NOTIFICATION (kind=voice_background_task_done)
     over SSE. `useGlobalEvents` dispatches `voice-bg-done` on window — the
     exact signal `VoiceSessionButton` listens for.

Shared-E2E Chrome runs many tabs, so SSE leadership may be held by another
tab (the page then consumes events via BroadcastChannel forwarding, which is
the real follower path). To make the stream observable deterministically from
this page, an invisible same-origin iframe opens its own EventSource and
forwards each real SSE frame through BroadcastChannel — mirroring exactly how
a leader tab broadcasts to followers. If this page itself wins leadership,
its own EventSource handles the events directly; both cases dispatch
`voice-bg-done` exactly once.

Also asserts the completion message lands in the chat timeline so the
ChatWindow refresh path is covered end to end.
"""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    navigate_mcp_page,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_VOICE_BG_DONE_LISTENER_JS = """(() => {
  window.__myrmVoiceBgDone = [];
  window.addEventListener('voice-bg-done', (event) => {
    window.__myrmVoiceBgDone.push({
      title: event.detail?.title ?? null,
      message: event.detail?.message ?? null,
      chat_id: event.detail?.chat_id ?? null,
      at: Date.now(),
    });
  });
  return { armed: true };
})()"""

_VOICE_BG_DONE_PROBE_JS = """(() => {
  const events = window.__myrmVoiceBgDone || [];
  const last = events.length > 0 ? events[events.length - 1] : null;
  return {
    ready: !!last,
    count: events.length,
    last,
  };
})()"""

_PAGE_DIAGNOSTIC_JS = """(() => {
  const resources = (performance.getEntriesByType('resource') || [])
    .map((r) => r.name)
    .filter((name) => name.includes('/notifications/stream'));
  return {
    href: window.location.href,
    hasChatBridge: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
    apiBase: window.__MYRM_E2E_RUNTIME__?.apiBase
      ?? window.__MYRM_E2E_API_BASE__
      ?? null,
    leader: localStorage.getItem('myrm-sse-leader') ?? null,
    sseResources: resources,
    bridgeOpen: window.__myrmBridgeOpen === true,
    bridgeErrors: window.__myrmBridgeErrors || [],
    bridgeFrames: (window.__myrmBridgeFrames || []).slice(-3),
    bcMessages: (window.__myrmBcMessages || []).slice(-3),
    sysNotifications: (window.__myrmSystemNotifications || []).slice(-5),
    voiceBgDoneCount: (window.__myrmVoiceBgDone || []).length,
  };
})()"""

_SYSTEM_NOTIFICATION_LISTENER_JS = """(() => {
  window.__myrmSystemNotifications = [];
  window.addEventListener('system-notification', (event) => {
    window.__myrmSystemNotifications.push({
      type: event.detail?.type ?? null,
      kind: event.detail?.data?.meta_data?.kind ?? null,
      at: Date.now(),
    });
  });
  return { armed: true };
})()"""

# Invisible same-origin iframe bridge: opens a real EventSource and forwards
# each SSE frame to BroadcastChannel so this page (when a follower) consumes
# the stream exactly like a leader tab broadcasting to followers.
# Warm-shell reuse may leave a previous test's bridge behind, so installing
# always tears down any prior EventSource/BroadcastChannel first.
_PIN_API_BASE_JS_TEMPLATE = """(() => {
  const target = '{api_base}';
  let changed = false;
  if (window.__MYRM_E2E_API_BASE__ !== target) {
    window.__MYRM_E2E_API_BASE__ = target;
    changed = true;
  }
  if (
    window.__MYRM_E2E_RUNTIME__ &&
    typeof window.__MYRM_E2E_RUNTIME__ === 'object' &&
    window.__MYRM_E2E_RUNTIME__.apiBase !== target
  ) {
    window.__MYRM_E2E_RUNTIME__.apiBase = target;
    changed = true;
  }
  return {
    changed,
    apiBase: window.__MYRM_E2E_RUNTIME__?.apiBase ?? window.__MYRM_E2E_API_BASE__,
  };
})()"""

_SSE_BRIDGE_INSTALL_JS_TEMPLATE = """(() => {
  window.__myrmBridgeFrames = [];
  window.__myrmBcMessages = [];
  window.__myrmBridgeErrors = [];
  window.__myrmBridgeOpen = false;
  window.__myrmSseBridgeInstalled = true;
  try {
    if (window.__myrmBridgeEs) {
      window.__myrmBridgeEs.close();
      window.__myrmBridgeEs = null;
    }
    if (window.__myrmBridgeBc) {
      window.__myrmBridgeBc.close();
      window.__myrmBridgeBc = null;
    }
    if (window.__myrmBridgePageBc) {
      window.__myrmBridgePageBc.close();
      window.__myrmBridgePageBc = null;
    }
  } catch (e) {
    window.__myrmBridgeErrors.push('teardown:' + String(e));
  }
  try {
    const frame = document.createElement('iframe');
    frame.style.display = 'none';
    frame.setAttribute('aria-hidden', 'true');
    document.body.appendChild(frame);
    const fw = frame.contentWindow;
    const bc = new fw.BroadcastChannel('myrm-sse-events');
    window.__myrmBridgeBc = bc;
    const es = new fw.EventSource('{sse_url}');
    window.__myrmBridgeEs = es;
    es.onopen = () => {
      window.__myrmBridgeOpen = true;
    };
    es.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data);
        window.__myrmBridgeFrames.push({ type: payload.type, at: Date.now() });
        bc.postMessage({ kind: 'sse-event', payload });
      } catch (e) {
        window.__myrmBridgeErrors.push('parse:' + String(e));
      }
    };
    es.onerror = () => {
      window.__myrmBridgeErrors.push('es-error:' + es.readyState);
    };
    const pageBc = new fw.BroadcastChannel('myrm-sse-events');
    window.__myrmBridgePageBc = pageBc;
    pageBc.onmessage = (ev) => {
      window.__myrmBcMessages.push({ kind: ev.data?.kind, at: Date.now() });
    };
    return { installed: true };
  } catch (e) {
    return { installed: false, error: String(e) };
  }
})()"""

_CHAT_MESSAGE_VISIBLE_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    ready: /E2E voice background task result/.test(text),
    textSample: text.slice(0, 600),
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(480)
def test_voice_background_done_dispatches_announce_event() -> None:
    api_base = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_base)
    warm_ui_route("/agents")

    # Warm-shell claim may land on a stale tab whose E2E bridge never attaches
    # (settings skeleton + fallback bridge). Retry the open so the orchestrator
    # claims a healthy shell instead of failing the whole test.
    last_open_error: BaseException | None = None
    for attempt in range(1, 4):
        try:
            with open_mcp_page(f"{ui_url}/agents", timeout_ms=120_000) as (client, page):
                dismiss_blocking_modals(client, page)
                diag = client.evaluate(page, _PAGE_DIAGNOSTIC_JS, timeout_sec=10.0)
                assert isinstance(diag, dict), diag
                if diag.get("hasChatBridge") is not True:
                    raise RuntimeError(f"warm shell lacks chat bridge: {diag}")
                print(
                    f"[voice-bg-e2e] attempt={attempt} api_base={api_base} "
                    f"href={diag.get('href')} leader={diag.get('leader')} "
                    f"sse_resources={diag.get('sseResources')}",
                    flush=True,
                )

                # Arm listeners first so no event is missed.
                armed = client.evaluate(page, _VOICE_BG_DONE_LISTENER_JS, timeout_sec=10.0)
                assert armed.get("armed") is True, armed
                sys_armed = client.evaluate(page, _SYSTEM_NOTIFICATION_LISTENER_JS, timeout_sec=10.0)
                assert sys_armed.get("armed") is True, sys_armed

                # Warm-shell reuse may leave a SHPOIB private apiBase on this page while
                # this SHARED test targets the shared backend. Pin the page bindings so
                # any SSE the page opens (own leader connection or retry) targets the
                # same backend the seed endpoint uses.
                pinned = client.evaluate(
                    page,
                    _PIN_API_BASE_JS_TEMPLATE.replace("{api_base}", api_base),
                    timeout_sec=10.0,
                )
                assert isinstance(pinned, dict) and str(pinned.get("apiBase") or "").rstrip("/") == api_base.rstrip("/"), pinned

                # Install the SSE bridge so real stream frames reach this page through
                # BroadcastChannel regardless of which tab owns SSE leadership.
                bridge_install = client.evaluate(
                    page,
                    _SSE_BRIDGE_INSTALL_JS_TEMPLATE.replace("{sse_url}", f"{api_base}/api/v1/notifications/stream"),
                    timeout_sec=10.0,
                )
                assert bridge_install.get("installed") is True, bridge_install

                # Wait until the stream is observable (bridge open AND has received at
                # least one real SSE frame, own EventSource, or forwarded notifications).
                stream_deadline = time.monotonic() + 30.0
                ready = False
                while time.monotonic() < stream_deadline:
                    diag = client.evaluate(page, _PAGE_DIAGNOSTIC_JS, timeout_sec=10.0)
                    if isinstance(diag, dict):
                        bridge_frames = diag.get("bridgeFrames") or []
                        if (
                            (diag.get("bridgeOpen") is True and len(bridge_frames) > 0)
                            or diag.get("sseResources")
                            or diag.get("sysNotifications")
                        ):
                            ready = True
                            break
                    time.sleep(1.0)
                print(
                    f"[voice-bg-e2e] stream_ready={ready} "
                    f"bridge_open={diag.get('bridgeOpen') if isinstance(diag, dict) else None} "
                    f"sse_resources={diag.get('sseResources') if isinstance(diag, dict) else []}",
                    flush=True,
                )
                # Let the SSE connection reconcile before seeding.
                time.sleep(1.0)

                seed = http_json(
                    "POST",
                    f"{api_base}/api/v1/background-tasks/test/seed-voice-done",
                )
                assert isinstance(seed, dict)
                chat_id = str(seed.get("chat_id") or "")
                assert chat_id.startswith("e2evoice")
                task_id = str(seed.get("task_id") or "")
                assert task_id.startswith("voice-e2e")

                deadline = time.monotonic() + 90.0
                last: dict[str, object] = {}
                while time.monotonic() < deadline:
                    state = client.evaluate(page, _VOICE_BG_DONE_PROBE_JS, timeout_sec=10.0)
                    if isinstance(state, dict):
                        last = state
                        if state.get("ready") is True:
                            break
                    time.sleep(0.5)

                if last.get("ready") is not True:
                    diag = client.evaluate(page, _PAGE_DIAGNOSTIC_JS, timeout_sec=10.0)
                    print(f"[voice-bg-e2e] FAILED diag={diag}", flush=True)
                assert last.get("ready") is True, last
                detail = last.get("last")
                assert isinstance(detail, dict), last
                assert str(detail.get("chat_id") or "") == chat_id, last
                assert detail.get("title"), last

                # Navigate to the seeded chat; ChatWindow must show the completion line
                # that WebuiVoiceWorkNotifier appended.
                navigate_mcp_page(
                    client,
                    page,
                    f"{ui_url}/{chat_id}",
                    timeout_ms=60_000,
                )
                message_ready = wait_for_state(client, page, _CHAT_MESSAGE_VISIBLE_JS, timeout_sec=60.0)
                assert message_ready.get("ready") is True, message_ready
            break
        except (RuntimeError, TimeoutError, AssertionError) as exc:
            last_open_error = exc
            print(
                f"[voice-bg-e2e] attempt={attempt} failed: {type(exc).__name__}: {str(exc)[:220]}",
                flush=True,
            )
            time.sleep(3.0)
    else:
        raise RuntimeError(f"all warm-shell open attempts failed: {last_open_error}")
