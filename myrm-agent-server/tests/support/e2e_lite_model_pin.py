"""Pin LITE_MODEL from .env.test for LIVE Chrome E2E (SSOT: dev_gate_contract + seed)."""

from __future__ import annotations

from tests.api.agent.utils import get_lite_model_selection

try:
    from mcp_chat_ui import McpChatSession
except ImportError:  # pragma: no cover - import path in pytest vs standalone
    McpChatSession = object  # type: ignore[misc,assignment]

PIN_LITE_MODEL_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) {
    return { ok: false, err: 'no-bridge' };
  }
  try {
    const pinned = await bridge.pinLiteModelForE2e();
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


def strip_provider_prefix(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[1]
    return model


async def pin_lite_model_for_e2e(
    chat: McpChatSession,
    *,
    recv_timeout: float = 30.0,
) -> dict[str, object]:
    """Pin lite model via E2E bridge; assert against get_lite_model_selection()."""
    pinned_raw = await chat.evaluate(  # type: ignore[attr-defined]
        PIN_LITE_MODEL_JS,
        await_promise=True,
        recv_timeout=recv_timeout,
    )
    assert isinstance(pinned_raw, dict), f"pinLiteModelForE2e returned non-dict: {pinned_raw}"
    assert pinned_raw.get("ok") is True, f"Failed to pin lite model for E2E: {pinned_raw}"
    expected = get_lite_model_selection()
    pinned_model = pinned_raw.get("pinned")
    assert isinstance(pinned_model, dict), f"Missing pinned model payload: {pinned_raw}"
    assert pinned_model.get("providerId") == expected["providerId"], (
        f"Pinned provider mismatch: {pinned_model} vs {expected}"
    )
    assert pinned_model.get("model") == strip_provider_prefix(str(expected["model"])), (
        f"Pinned model mismatch: {pinned_model} vs {expected}"
    )
    return pinned_raw
