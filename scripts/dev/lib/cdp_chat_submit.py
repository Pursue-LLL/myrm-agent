"""Chat submit workflow with deterministic UI fallbacks."""

from __future__ import annotations

import asyncio
import json
import time

from cdp_chat_input import CdpChatInput
from cdp_chat_support import PREPARE_AUTOMATION_SEND_JS, get_e2e_api_url


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
        result = await self.evaluate(
            f"""(() => {{
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.sendChatMessage) {{
                return {{ ok: false, err: 'no-sendChatMessage' }};
              }}
              return Promise.resolve(
                bridge.sendChatMessage({payload}, {{ baselineUserCount: {baseline} }}),
              );
            }})()""",
            await_promise=True,
            recv_timeout=180.0,
        )
        return (
            result
            if isinstance(result, dict)
            else {"ok": False, "err": "atomic-send-invalid"}
        )

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
                await_promise=False,
            )
            if isinstance(probe, dict):
                last = probe
                if probe.get("hasBtn") and not probe.get("disabled"):
                    return {"ok": True, **probe}
            await asyncio.sleep(poll_interval_sec)
        return {"ok": False, "err": "send-button-not-ready", **last}

    async def submit_native_click(self) -> dict[str, object]:
        """Click the send button when the E2E bridge sendChatMessage hook is unavailable."""
        ready = await self.wait_send_button_ready(timeout_sec=60.0)
        if not ready.get("ok"):
            return {"ok": False, "err": "no send button", "probe": ready}
        await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
        native = await self.evaluate(
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn) return { ok: false, err: 'no send button' };
              if (btn.disabled) return { ok: false, err: 'send disabled' };
              btn.click();
              return { ok: true, mode: 'nativeClick' };
            })()""",
            await_promise=False,
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
        msg_payload = json.dumps(message_text) if message_text is not None else "null"
        baseline_payload = int(baseline_user_msgs)
        baseline_payload = int(baseline_user_msgs)
        if message_text is not None:
            result = await self.evaluate(
                f"""(() => {{
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (!bridge?.sendChatMessage) {{
                    return {{ ok: false, err: 'no-sendChatMessage' }};
                  }}
                  return Promise.resolve(
                    bridge.sendChatMessage({msg_payload}, {{ baselineUserCount: {baseline_payload} }}),
                  );
                }})()""",
                await_promise=True,
                recv_timeout=180.0,
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
            await_promise=True,
            recv_timeout=120.0,
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
                await_promise=False,
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

    async def submit(
        self,
        message_text: str | None = None,
        *,
        baseline_user_msgs: int = 0,
    ) -> dict[str, object]:
        e2e_api = get_e2e_api_url().strip()
        if e2e_api:
            await self.ensure_e2e_api_base_binding()
            bridge_submit = await self._submit_via_dev_bridge(
                message_text,
                baseline_user_msgs=baseline_user_msgs,
            )
            started = await self._submit_started()
            if (
                isinstance(bridge_submit, dict)
                and bridge_submit.get("ok")
                and await self._stream_started(started)
            ):
                return bridge_submit
            if isinstance(bridge_submit, dict):
                return bridge_submit
            return {
                "ok": False,
                "err": "dev-bridge-submit-failed",
                "mode": "devBridgeRequired",
            }

        prefer_bridge = await self.evaluate(
            """(() => ({
              prefer: typeof window.__MYRM_E2E_API_BASE__ === 'string' && window.__MYRM_E2E_API_BASE__.trim().length > 0,
            }))()""",
            await_promise=False,
        )
        if isinstance(prefer_bridge, dict) and prefer_bridge.get("prefer"):
            bridge_submit = await self._submit_via_dev_bridge(
                message_text,
                baseline_user_msgs=baseline_user_msgs,
            )
            started = await self._submit_started()
            if (
                isinstance(bridge_submit, dict)
                and bridge_submit.get("ok")
                and await self._stream_started(started)
            ):
                return bridge_submit
            if isinstance(bridge_submit, dict):
                return bridge_submit
            return {
                "ok": False,
                "err": "dev-bridge-submit-failed",
                "mode": "devBridgeRequired",
            }

        await self.evaluate(PREPARE_AUTOMATION_SEND_JS, await_promise=False)
        native = await self.evaluate(
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn) return { ok: false, err: 'no send button' };
              if (btn.disabled) return { ok: false, err: 'send disabled' };
              btn.click();
              return { ok: true, mode: 'nativeClick' };
            })()""",
            await_promise=False,
        )
        if isinstance(native, dict) and native.get("ok"):
            started = await self._submit_started()
            if await self._stream_started(started):
                return native

        bridge_submit = await self._submit_via_dev_bridge(
            message_text,
            baseline_user_msgs=baseline_user_msgs,
        )
        if isinstance(bridge_submit, dict) and bridge_submit.get("ok"):
            started = await self._submit_started()
            if await self._stream_started(started):
                return bridge_submit

        if isinstance(native, dict) and native.get("ok"):
            await asyncio.sleep(1.5)
            started = await self._submit_started()
            if await self._stream_started(started):
                return native

        react_click = await self.evaluate(
            """(() => {
              const btn = document.querySelector('.message-send-btn');
              if (!btn || btn.disabled) return { ok: false, err: 'send disabled or missing' };
              const propsKey = Object.keys(btn).find((k) => k.startsWith('__reactProps$'));
              if (propsKey && btn[propsKey]?.onClick) {
                btn[propsKey].onClick({ preventDefault() {}, stopPropagation() {} });
                return { ok: true, mode: 'react-onClick' };
              }
              const fiberKey = Object.keys(btn).find((k) => k.startsWith('__reactFiber$'));
              if (fiberKey) {
                let fiber = btn[fiberKey];
                while (fiber) {
                  const onClick = fiber.memoizedProps?.onClick;
                  if (typeof onClick === 'function') {
                    onClick({ preventDefault() {}, stopPropagation() {} });
                    return { ok: true, mode: 'fiber-onClick' };
                  }
                  fiber = fiber.return;
                }
              }
              return { ok: false, err: 'no react handler' };
            })()""",
            await_promise=False,
        )
        if isinstance(react_click, dict) and react_click.get("ok"):
            await asyncio.sleep(1.0)
            started = await self._submit_started()
            if await self._stream_started(started):
                return react_click

        click = await self.evaluate(
            """(() => {
              const input = document.querySelector('[data-chat-input]');
              const form = input?.closest('form');
              if (form && typeof form.requestSubmit === 'function') {
                form.requestSubmit();
                return { ok: true, mode: 'requestSubmit' };
              }
              const btn =
                document.querySelector('button[aria-label="发送"]') ||
                document.querySelector('button[aria-label="Send"]') ||
                document.querySelector('.message-send-btn');
              if (!btn) return { ok: false, err: 'no send button' };
              if (btn.disabled) return { ok: false, err: 'send disabled' };
              btn.dispatchEvent(
                new MouseEvent('click', { bubbles: true, cancelable: true, view: window }),
              );
              return { ok: true, mode: 'dispatchClick' };
            })()""",
            await_promise=False,
        )
        await asyncio.sleep(1.0)
        started = await self._submit_started()
        if await self._stream_started(started):
            return click if isinstance(click, dict) else {"ok": True, "mode": "cleared"}

        await self.cdp("DOM.enable")
        doc = await self.cdp("DOM.getDocument")
        root_id = doc.get("root", {}).get("nodeId")
        query = await self.cdp(
            "DOM.querySelector",
            {"nodeId": root_id, "selector": ".message-send-btn:not([disabled])"},
        )
        node_id = query.get("nodeId")
        if isinstance(node_id, int) and node_id > 0:
            try:
                box = await self.cdp("DOM.getBoxModel", {"nodeId": node_id})
                content = (
                    box.get("model", {}).get("content")
                    if isinstance(box.get("model"), dict)
                    else None
                )
                if isinstance(content, list) and len(content) >= 6:
                    cx = (content[0] + content[2]) / 2
                    cy = (content[1] + content[5]) / 2
                    await self.cdp(
                        "Input.dispatchMouseEvent",
                        {
                            "type": "mousePressed",
                            "x": cx,
                            "y": cy,
                            "button": "left",
                            "clickCount": 1,
                        },
                    )
                    await self.cdp(
                        "Input.dispatchMouseEvent",
                        {
                            "type": "mouseReleased",
                            "x": cx,
                            "y": cy,
                            "button": "left",
                            "clickCount": 1,
                        },
                    )
                    await asyncio.sleep(1.5)
                    started = await self._submit_started()
                    if await self._stream_started(started):
                        return {"ok": True, "mode": "cdpMouseSend"}
            except RuntimeError:
                pass

        await self.cdp(
            "Input.dispatchKeyEvent",
            {
                "type": "keyDown",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
            },
        )
        await self.cdp(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
            },
        )
        await asyncio.sleep(1.5)
        started = await self._submit_started()
        if await self._stream_started(started):
            return {"ok": True, "mode": "enterKeyFallback"}

        started = await self._submit_started()
        if await self._stream_started(started):
            return {"ok": True, "mode": "postBridgeProbe", "started": started}
        bridge_result = await self.evaluate(
            """(() => ({
              lastSubmit: window.__MYRM_E2E_CHAT__?.lastSubmitResult ?? null,
              debug: window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null,
            }))()""",
            await_promise=False,
        )
        exhausted: dict[str, object] = {
            "ok": False,
            "mode": "submitExhausted",
            "started": started,
        }
        if isinstance(bridge_result, dict):
            exhausted["bridge"] = bridge_result
        return exhausted
