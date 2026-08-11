"""Chat submit via SendTurnContract atomic evaluate (R72)."""

from __future__ import annotations

import asyncio
import json
import sys
import time

from cdp_chat_input import CdpChatInput
from cdp_chat_support import PREPARE_AUTOMATION_SEND_JS
from dev_gate_contract import (
    EvaluateIntent,
    SEND_TURN_LOG_TOKEN,
    SEND_TURN_PYTHON_WALL_SEC,
)
from send_turn_contract import SendTurnError, SendTurnPhase, resolve_send_turn_profile


class CdpChatSubmit(CdpChatInput):
    async def send_chat_message_atomic(
        self,
        text: str,
        *,
        baseline_user_msgs: int = 0,
    ) -> dict[str, object]:
        await self.ensure_e2e_api_base_binding()
        payload = json.dumps(text)
        baseline = int(baseline_user_msgs)
        profile = resolve_send_turn_profile()
        profile_json = json.dumps(profile)
        try:
            result = await asyncio.wait_for(
                self.evaluate(
                    f"""(() => {{
                      const bridge = window.__MYRM_E2E_CHAT__;
                      const baseline = {baseline};
                      const text = {payload};
                      const profile = {profile_json};
                      if (typeof bridge?.submitAndObserveTurn === 'function') {{
                        return Promise.resolve(
                          bridge.submitAndObserveTurn(text, {{ baselineUserCount: baseline, profile }}),
                        );
                      }}
                      return {{ ok: false, err: 'no-submitAndObserveTurn', mode: 'sendTurnBridgeMissing' }};
                    }})()""",
                    intent=EvaluateIntent.AGENT_SUBMIT,
                ),
                timeout=SEND_TURN_PYTHON_WALL_SEC,
            )
        except asyncio.TimeoutError as exc:
            raise SendTurnError(
                SendTurnPhase.SUBMIT,
                "send-turn-evaluate-timeout",
                detail={"baseline": baseline, "profile": profile},
            ) from exc
        if isinstance(result, dict):
            debug = result.get("debug")
            if isinstance(debug, dict):
                phase = str(debug.get("phase") or "SUBMIT")
                chat_id = str(result.get("chatId") or "").strip()
                detail = (
                    f" apiUsers={debug.get('apiUsers')} "
                    f"userCount={debug.get('userCount')} "
                    f"streaming={debug.get('streaming')} "
                    f"baseline={debug.get('baselineUsers')} "
                    f"rev={debug.get('rev')}"
                )
                print(
                    f"{SEND_TURN_LOG_TOKEN}: phase={phase} ok={result.get('ok')} "
                    f"mode={result.get('mode')} chatId={chat_id or '-'} profile={profile}{detail}",
                    file=sys.stderr,
                    flush=True,
                )
            return result
        return {"ok": False, "err": "atomic-send-invalid"}

    async def wait_send_button_ready(
        self,
        *,
        timeout_sec: float = 60.0,
        poll_interval_sec: float = 0.5,
    ) -> dict[str, object]:
        """Poll until `.message-send-btn` exists and is enabled (post route-restore)."""
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {"hasBtn": False, "disabled": True}
        while time.monotonic() < deadline:
            probe = await self.evaluate(
                """(() => {
                  const btn = document.querySelector('.message-send-btn');
                  return {
                    hasBtn: Boolean(btn),
                    disabled: btn ? Boolean(btn.disabled) : true,
                    sendReady: !!window.__MYRM_E2E_CHAT__?.isSendReady?.(),
                    href: String(location.href || ''),
                  };
                })()""",
                intent=EvaluateIntent.SYNC_PROBE,
            )
            if isinstance(probe, dict):
                last = probe
                if probe.get("hasBtn") and not probe.get("disabled"):
                    return {"ok": True, **probe}
                if probe.get("sendReady") and not probe.get("hasBtn"):
                    return {
                        "ok": False,
                        "err": "no send button",
                        "sendReady": True,
                        **probe,
                    }
            await asyncio.sleep(poll_interval_sec)
        return {"ok": False, "err": "send-button-not-ready", **last}

    async def submit_native_click(self) -> dict[str, object]:
        """Click `.message-send-btn` for desktop fast-native fallback paths."""
        ready = await self.wait_send_button_ready(timeout_sec=60.0)
        if not ready.get("ok"):
            return {"ok": False, "err": "no send button", "probe": ready}
        await self.evaluate(
            PREPARE_AUTOMATION_SEND_JS, intent=EvaluateIntent.SYNC_PROBE
        )
        native = await self.evaluate(
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn) return { ok: false, err: 'no send button' };
              if (btn.disabled) return { ok: false, err: 'send disabled' };
              btn.click();
              return { ok: true, mode: 'nativeClick' };
            })()""",
            intent=EvaluateIntent.SYNC_PROBE,
        )
        return (
            native
            if isinstance(native, dict)
            else {"ok": False, "err": "native-click-invalid"}
        )

    async def _submit_via_dev_bridge(
        self,
        message_text: str | None = None,
        *,
        baseline_user_msgs: int = 0,
    ) -> dict[str, object]:
        await self.ensure_e2e_api_base_binding()
        baseline_payload = int(baseline_user_msgs)
        if message_text is not None:
            payload = json.dumps(message_text)
            baseline = int(baseline_payload)
            profile = json.dumps(resolve_send_turn_profile())
            result = await self.evaluate(
                f"""(() => {{
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (typeof bridge?.submitAndObserveTurn !== 'function') {{
                    return {{ ok: false, err: 'no-submitAndObserveTurn', mode: 'sendTurnBridgeMissing' }};
                  }}
                  return Promise.resolve(
                    bridge.submitAndObserveTurn({payload}, {{
                      baselineUserCount: {baseline},
                      profile: {profile},
                    }}),
                  );
                }})()""",
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
            return (
                result
                if isinstance(result, dict)
                else {"ok": False, "err": "bridge-submit-invalid"}
            )

        dev_submit = await self.evaluate(
            f"""(() => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.handleSubmit) {{
                return {{ ok: false, err: 'no dev bridge' }};
              }}
              bridge._submitBaselineUsers = {baseline_payload};
              return Promise.resolve(bridge.handleSubmit()).then(() => {{
                const result = bridge.lastSubmitResult;
                if (result?.ok) {{
                  return {{ ok: true, mode: 'devBridgeSubmitAsync', result }};
                }}
                return {{
                  ok: false,
                  err: result?.err || 'bridge-submit-failed',
                  debug: result?.debug ?? null,
                  mode: 'devBridgeSubmitFailed',
                }};
              }});
            }})()""",
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        if not (isinstance(dev_submit, dict) and dev_submit.get("ok")):
            return (
                dev_submit
                if isinstance(dev_submit, dict)
                else {"ok": False, "err": "dev-bridge-submit-failed"}
            )

        started = await self._submit_started()
        if await self._stream_started(started):
            return dev_submit

        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            await asyncio.sleep(1.5)
            bridge_result = await self.evaluate(
                """(() => window.__MYRM_E2E_CHAT__?.lastSubmitResult ?? null)()""",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            if isinstance(bridge_result, dict) and bridge_result.get("ok") is False:
                err = str(bridge_result.get("err") or "bridge-submit-failed")
                if err in {"send-not-ready", "no-chat-id", "empty-message"}:
                    await asyncio.sleep(0.5)
                    continue
            started = await self._submit_started()
            if await self._stream_started(started):
                return dev_submit
        return dev_submit
