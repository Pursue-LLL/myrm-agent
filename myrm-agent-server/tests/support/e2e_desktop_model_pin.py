"""Pin BASIC_MODEL for desktop Chrome E2E (snapshot→interact tool chain).

v48 LIVE PASS used mimo-v2.5-pro (BASIC); LITE MiniMax-M3 often stops after snapshot.
"""

from __future__ import annotations

import asyncio

from tests.api.agent.utils import get_model_selection
from tests.support.e2e_lite_model_pin import strip_provider_prefix

try:
    from mcp_chat_ui import McpChatSession
except ImportError:  # pragma: no cover - import path in pytest vs standalone
    McpChatSession = object  # type: ignore[misc,assignment]

PROVIDER_ALREADY_PINNED_JS = """(() => {
  const debug = window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null;
  if (!debug) {
    return { ok: false, err: 'no-bridge' };
  }
  const selection = debug.selection ?? debug.primary ?? null;
  if (!selection?.providerId || !selection?.model) {
    return { ok: false, err: 'no-selection' };
  }
  return {
    ok: true,
    alreadyPinned: true,
    pinned: {
      providerId: selection.providerId,
      model: selection.model,
    },
    selection,
    agentModelSelection: debug.agentModelSelection ?? null,
  };
})()"""

PIN_BASIC_MODEL_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinBasicModelForE2e) {
    return { ok: false, err: 'no-bridge' };
  }
  if (bridge.ensureProviders) {
    await bridge.ensureProviders();
  }
  try {
    const pinned = await bridge.pinBasicModelForE2e();
    const debug = bridge.debugProviderState?.() ?? {};
    return {
      ok: true,
      pinned,
      selection: debug.selection ?? null,
      agentModelSelection: debug.agentModelSelection ?? null,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


def _assert_pinned_payload(
    pinned_raw: dict[str, object],
) -> dict[str, object]:
    expected = get_model_selection()
    pinned_model = pinned_raw.get("pinned")
    assert isinstance(
        pinned_model, dict
    ), f"Missing pinned model payload: {pinned_raw}"
    assert (
        pinned_model.get("providerId") == expected["providerId"]
    ), f"Pinned provider mismatch: {pinned_model} vs {expected}"
    assert pinned_model.get("model") == strip_provider_prefix(
        str(expected["model"])
    ), f"Pinned model mismatch: {pinned_model} vs {expected}"
    return pinned_raw


async def pin_basic_model_for_desktop_e2e(
    chat: McpChatSession,
    *,
    recv_timeout: float = 120.0,
    max_attempts: int = 5,
    retry_sleep_sec: float = 3.0,
) -> dict[str, object]:
    """Pin BASIC model via E2E bridge; assert against get_model_selection()."""
    last_raw: object = None
    for attempt in range(1, max_attempts + 1):
        fast_raw = await chat.evaluate(  # type: ignore[attr-defined]
            PROVIDER_ALREADY_PINNED_JS,
            await_promise=False,
            recv_timeout=min(recv_timeout, 30.0),
        )
        if isinstance(fast_raw, dict) and fast_raw.get("ok") is True:
            return _assert_pinned_payload(fast_raw)

        pinned_raw = await chat.evaluate(  # type: ignore[attr-defined]
            PIN_BASIC_MODEL_JS,
            await_promise=True,
            recv_timeout=recv_timeout,
        )
        last_raw = pinned_raw
        if isinstance(pinned_raw, dict) and pinned_raw.get("ok") is True:
            return _assert_pinned_payload(pinned_raw)
        err = (
            str(pinned_raw.get("err") or pinned_raw)
            if isinstance(pinned_raw, dict)
            else str(pinned_raw)
        )
        if attempt < max_attempts and (
            "e2e-base-model-unconfigured" in err
            or "e2e-base-model-unavailable" in err
            or err in {"no-bridge", "no-selection"}
        ):
            if err in {"no-bridge", "no-selection"}:
                await chat.ensure_react_e2e_bridge(timeout_sec=120.0)  # type: ignore[attr-defined]
            await asyncio.sleep(retry_sleep_sec)
            continue
        raise AssertionError(
            f"Failed to pin BASIC model for desktop E2E after {attempt} attempts: {last_raw}"
        )
    raise AssertionError(
        f"Failed to pin BASIC model for desktop E2E: {last_raw}"
    )
