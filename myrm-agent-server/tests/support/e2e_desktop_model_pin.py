"""Pin BASIC_MODEL for desktop Chrome E2E (snapshot→interact tool chain).

v48 LIVE PASS used mimo-v2.5-pro (BASIC); LITE MiniMax-M3 often stops after snapshot.
"""

from __future__ import annotations

import asyncio

from tests.api.agent.utils import get_model_selection
from tests.support.chrome_mcp_e2e import get_e2e_ui_url
from tests.support.e2e_lite_model_pin import strip_provider_prefix

try:
    from mcp_chat_ui import McpChatSession
except ImportError:  # pragma: no cover - import path in pytest vs standalone
    McpChatSession = object  # type: ignore[misc,assignment]

try:
    from dev_gate_contract import EvaluateIntent, resolve_evaluate_budget
except ImportError:  # pragma: no cover - import path in pytest vs standalone
    EvaluateIntent = None  # type: ignore[misc,assignment]

    def resolve_evaluate_budget(intent):  # type: ignore[misc]
        from types import SimpleNamespace

        return SimpleNamespace(cdp_timeout_sec=60.0)

DEBUG_PROVIDER_STATE_JS = (
    """(() => window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null)()"""
)

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

SYNC_PROVIDER_BRIDGE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.prepareAutomationSend?.();
  if (!bridge?.ensureProviders) {
    return bridge?.debugProviderState?.() ?? null;
  }
  return Promise.resolve(bridge.ensureProviders()).then(
    () => bridge.debugProviderState?.() ?? null,
  );
})()"""

_TRANSIENT_PROVIDER_PIN_ERROR_TOKENS: tuple[str, ...] = (
    "e2e-send-not-ready-after-provider-init",
    "transport closed",
    "transport unavailable",
    "request lock",
    "timeout",
)


def _expected_model_selection() -> dict[str, object]:
    return get_model_selection()


def _is_transient_provider_pin_error(message: str) -> bool:
    normalized = message.strip().lower()
    if not normalized:
        return False
    return any(token in normalized for token in _TRANSIENT_PROVIDER_PIN_ERROR_TOKENS)


async def _evaluate_bridge(
    chat: McpChatSession,
    script: str,
    *,
    intent: EvaluateIntent,
) -> object:
    budget = resolve_evaluate_budget(intent)
    wall_timeout = max(30.0, budget.cdp_timeout_sec + 15.0)
    try:
        return await asyncio.wait_for(
            chat.evaluate(  # type: ignore[attr-defined]
                script,
                intent=intent,
            ),
            timeout=wall_timeout,
        )
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            "desktop model pin bridge evaluate wall-timeout "
            f"({wall_timeout:.0f}s intent={intent.value})"
        ) from exc


async def _recover_provider_bridge(chat: McpChatSession) -> None:
    await chat.ensure_chat_surface(get_e2e_ui_url(), timeout_sec=90.0)  # type: ignore[attr-defined]
    await chat.ensure_react_e2e_bridge(timeout_sec=120.0)  # type: ignore[attr-defined]


def expected_desktop_e2e_model() -> dict[str, str]:
    """Return the provider/model pair desktop E2E must use before agent send."""
    expected = _expected_model_selection()
    return {
        "providerId": str(expected["providerId"]),
        "model": strip_provider_prefix(str(expected["model"])),
    }


def ui_selection_from_provider_debug(debug: dict[str, object]) -> dict[str, str] | None:
    """Read the effective UI send model from debugProviderState()."""
    for key in ("selection", "agentModelSelection", "primary"):
        raw = debug.get(key)
        if not isinstance(raw, dict):
            continue
        provider_id = str(raw.get("providerId") or "").strip()
        model = str(raw.get("model") or "").strip()
        if provider_id and model:
            return {"providerId": provider_id, "model": model}
    return None


def ui_provider_debug_matches_expected(debug: dict[str, object]) -> bool:
    """True when UI getModelSelection SSOT matches desktop E2E BASIC expectation."""
    expected = expected_desktop_e2e_model()
    ui = ui_selection_from_provider_debug(debug)
    if ui is None:
        return False
    return (
        ui["providerId"] == expected["providerId"] and ui["model"] == expected["model"]
    )


def _assert_pinned_payload(pinned_raw: dict[str, object]) -> dict[str, object]:
    expected = expected_desktop_e2e_model()
    pinned_model = pinned_raw.get("pinned")
    assert isinstance(pinned_model, dict), f"Missing pinned model payload: {pinned_raw}"
    assert (
        pinned_model.get("providerId") == expected["providerId"]
    ), f"Pinned provider mismatch: {pinned_raw} vs {expected}"
    assert (
        pinned_model.get("model") == expected["model"]
    ), f"Pinned model mismatch: {pinned_raw} vs {expected}"
    return pinned_raw


async def fetch_ui_provider_debug(
    chat: McpChatSession,
) -> dict[str, object]:
    raw = await _evaluate_bridge(
        chat,
        DEBUG_PROVIDER_STATE_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    return raw if isinstance(raw, dict) else {}


async def ensure_desktop_basic_model_pinned_for_send(
    chat: McpChatSession,
    *,
    max_attempts: int = 5,
    retry_sleep_sec: float = 3.0,
) -> dict[str, object]:
    """Pin BASIC_MODEL and verify UI selection before desktop agent send."""
    expected = expected_desktop_e2e_model()
    last_debug: dict[str, object] = {}
    last_raw: object = None
    for attempt in range(1, max_attempts + 1):
        try:
            last_debug = await fetch_ui_provider_debug(chat)
        except (RuntimeError, TimeoutError, OSError) as exc:
            err = str(exc)
            if attempt < max_attempts and _is_transient_provider_pin_error(err):
                try:
                    await _recover_provider_bridge(chat)
                except (RuntimeError, TimeoutError, OSError):
                    pass
                await asyncio.sleep(retry_sleep_sec)
                continue
            raise AssertionError(
                "Desktop E2E provider debug probe failed before pin "
                f"(attempt {attempt}/{max_attempts}): {err}"
            ) from exc
        if ui_provider_debug_matches_expected(last_debug):
            return {
                "ok": True,
                "attempt": attempt,
                "debug": last_debug,
                "alreadyPinned": True,
            }

        pin_eval_error = ""
        try:
            pinned_raw = await _evaluate_bridge(
                chat,
                PIN_BASIC_MODEL_JS,
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            pin_eval_error = str(exc)
            pinned_raw = {"ok": False, "err": pin_eval_error}
        last_raw = pinned_raw
        if isinstance(pinned_raw, dict) and pinned_raw.get("ok") is True:
            _assert_pinned_payload(pinned_raw)
            try:
                last_debug = await fetch_ui_provider_debug(chat)
            except (RuntimeError, TimeoutError, OSError) as exc:
                pin_eval_error = str(exc)
                last_debug = {}
            if ui_provider_debug_matches_expected(last_debug):
                return {
                    "ok": True,
                    "attempt": attempt,
                    "debug": last_debug,
                    "pinned": pinned_raw,
                }

        sync_eval_error = ""
        try:
            sync_raw = await _evaluate_bridge(
                chat,
                SYNC_PROVIDER_BRIDGE_JS,
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            sync_eval_error = str(exc)
            sync_raw = {"ok": False, "err": sync_eval_error}
        if isinstance(sync_raw, dict):
            last_debug = sync_raw
            if ui_provider_debug_matches_expected(last_debug):
                return {
                    "ok": True,
                    "attempt": attempt,
                    "debug": last_debug,
                    "synced": True,
                }

        err = ""
        if isinstance(pinned_raw, dict):
            err = str(pinned_raw.get("err") or "")
        if not err:
            err = pin_eval_error or sync_eval_error
        normalized_err = err.strip().lower()
        bridge_missing = normalized_err == "no-bridge" or "no-bridge" in normalized_err
        no_selection = (
            normalized_err == "no-selection" or "no-selection" in normalized_err
        )
        should_retry = (
            "e2e-base-model-unconfigured" in err
            or "e2e-base-model-unavailable" in err
            or bridge_missing
            or no_selection
            or _is_transient_provider_pin_error(err)
        )
        if attempt < max_attempts and (should_retry):
            if bridge_missing or no_selection or _is_transient_provider_pin_error(err):
                try:
                    await _recover_provider_bridge(chat)
                except (RuntimeError, TimeoutError, OSError):
                    pass
            await asyncio.sleep(retry_sleep_sec)
            continue
        if bridge_missing or no_selection:
            raise RuntimeError(
                "Dev E2E chat bridge not available on WebUI during BASIC model pin "
                f"(attempt {attempt}/{max_attempts}, err={err!r}, debug={last_debug!r})"
            )

        ui = ui_selection_from_provider_debug(last_debug)
        raise AssertionError(
            "Desktop E2E BASIC model pin failed before send "
            f"(attempt {attempt}/{max_attempts}): expected={expected} "
            f"ui_selection={ui!r} pin={last_raw!r} debug={last_debug!r}"
        )

    raise AssertionError(
        f"Desktop E2E BASIC model pin failed: expected={expected} debug={last_debug!r}"
    )


async def pin_basic_model_for_desktop_e2e(
    chat: McpChatSession,
    *,
    max_attempts: int = 5,
    retry_sleep_sec: float = 3.0,
) -> dict[str, object]:
    """Pin BASIC_MODEL for desktop E2E."""
    result = await ensure_desktop_basic_model_pinned_for_send(
        chat,
        max_attempts=max_attempts,
        retry_sleep_sec=retry_sleep_sec,
    )
    pinned = result.get("pinned")
    if isinstance(pinned, dict):
        return pinned
    debug = result.get("debug")
    if isinstance(debug, dict):
        ui = ui_selection_from_provider_debug(debug)
        if ui is not None:
            return {"ok": True, "pinned": ui, "debug": debug}
    return {"ok": True, **result}
