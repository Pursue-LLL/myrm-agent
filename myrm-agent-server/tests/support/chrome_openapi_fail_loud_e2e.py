"""Shared Chrome E2E helpers for OpenAPI fail-loud chat assertions."""

from __future__ import annotations

import json

WAIT_CHAT_IDLE_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const turn = bridge.turnSnapshot?.() ?? {};
    if (!turn.isStreaming) {
      return { ok: true, turn };
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return { ok: false, err: 'chat-still-streaming', turn: bridge.turnSnapshot?.() ?? null };
})()"""


def wait_agent_applied_js(expected_agent_id: str) -> str:
    agent_id_json = json.dumps(expected_agent_id)
    return f"""(async () => {{
  const expectedAgentId = {agent_id_json};
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {{
    const state = window.__myrmChatStore?.getState?.();
    const agentId = state?.agentConfig?.agentId ?? null;
    const actionMode = state?.actionMode ?? null;
    if (agentId === expectedAgentId && actionMode === 'agent') {{
      return {{ ok: true, agentId, actionMode }};
    }}
    window.__MYRM_E2E_CHAT__?.setActionMode?.('agent');
    await new Promise((resolve) => setTimeout(resolve, 500));
  }}
  const state = window.__myrmChatStore?.getState?.();
  return {{
    ok: false,
    err: 'agent-not-applied',
    agentId: state?.agentConfig?.agentId ?? null,
    actionMode: state?.actionMode ?? null,
  }};
}})()"""


PREPARE_AGENT_CHAT_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  bridge.setActionMode?.('agent');
  if (typeof bridge.ensureProviders === 'function') {
    await bridge.ensureProviders();
  }
  if (typeof bridge.pinBasicModelForE2e === 'function') {
    await bridge.pinBasicModelForE2e();
  } else if (typeof bridge.pinLiteModelForE2e === 'function') {
    await bridge.pinLiteModelForE2e();
  }
  bridge.clearSseSnapshot?.();
  const state = window.__myrmChatStore?.getState?.();
  return {
    ok: !!bridge.isSendReady?.(),
    sendReady: !!bridge.isSendReady?.(),
    agentId: state?.agentConfig?.agentId ?? null,
    actionMode: state?.actionMode ?? null,
  };
})()"""


def send_and_wait_openapi_error_js(
    *,
    expected_error_type: str,
    message_pattern: str,
) -> str:
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return {{ ok: false, err: 'no-bridge' }};
  const expectedErrorType = {json.dumps(expected_error_type)};
  const pattern = /{message_pattern}/i;
  bridge.setActionMode?.('agent');
  bridge.clearSseSnapshot?.();
  const idleBefore = await ({WAIT_CHAT_IDLE_JS});
  if (!idleBefore?.ok) {{
    return {{ ok: false, err: 'idle-before-send-failed', idleBefore }};
  }}
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  let result;
  if (typeof bridge.sendChatMessage === 'function') {{
    result = await bridge.sendChatMessage('hello', {{ baselineUserCount: usersBefore }});
  }} else {{
    return {{ ok: false, err: 'no-sendChatMessage' }};
  }}
  if (!result?.ok) {{
    return {{ ok: false, err: 'send-failed', send: result }};
  }}
  const readChatErrorType = () => {{
    const messages = window.__myrmChatStore?.getState?.()?.messages ?? [];
    for (const msg of messages) {{
      const metaType = msg?.metadata?.error_type;
      if (typeof metaType === 'string' && metaType === expectedErrorType) {{
        return {{ matched: 'metadata', errorType: metaType }};
      }}
      const steps = msg?.progressSteps ?? [];
      for (const step of steps) {{
        if (step?.step_key !== 'processing_failed') continue;
        const text = String(step?.items?.[0]?.text ?? '');
        if (pattern.test(text)) {{
          return {{ matched: 'progressStep', errorType: metaType ?? null, text }};
        }}
      }}
    }}
    return null;
  }};
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline) {{
    const turn = bridge.turnSnapshot?.() ?? {{}};
    const chatHit = readChatErrorType();
    const sse = bridge.sseSnapshot?.() ?? [];
    if (chatHit) {{
      return {{
        ok: true,
        ...chatHit,
        sseHasError: sse.includes('error'),
        streaming: turn.isStreaming === true,
        send: result,
        sse,
      }};
    }}
    if (!turn.isStreaming && sse.includes('error')) {{
      const retryHit = readChatErrorType();
      if (retryHit) {{
        return {{
          ok: true,
          ...retryHit,
          sseHasError: true,
          streaming: false,
          send: result,
          sse,
        }};
      }}
    }}
    await new Promise((resolve) => setTimeout(resolve, 300));
  }}
  const messages = window.__myrmChatStore?.getState?.()?.messages ?? [];
  const turn = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: false,
    err: 'no-openapi-error-visible',
    send: result,
    sse: bridge.sseSnapshot?.() ?? [],
    messageMeta: messages.map((m) => m?.metadata ?? null),
    progressSteps: messages.map((m) => m?.progressSteps ?? null),
    streaming: turn.isStreaming === true,
    actionMode: window.__myrmChatStore?.getState?.()?.actionMode ?? null,
    agentId: window.__myrmChatStore?.getState?.()?.agentConfig?.agentId ?? null,
  }};
}})()"""
