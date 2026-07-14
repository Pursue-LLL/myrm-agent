"""Chat submit workflow with deterministic UI fallbacks."""

from __future__ import annotations

import asyncio
import time

from cdp_chat_input import CdpChatInput


class CdpChatSubmit(CdpChatInput):
    async def submit(self) -> dict[str, object]:
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

        dev_submit = await self.evaluate(
            """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.handleSubmit) {
                return { ok: false, err: 'no dev bridge' };
              }
              void bridge.handleSubmit();
              return { ok: true, mode: 'devBridgeSubmitAsync' };
            })()""",
            await_promise=False,
        )
        if isinstance(dev_submit, dict) and dev_submit.get("ok"):
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
                content = box.get("model", {}).get("content") if isinstance(box.get("model"), dict) else None
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
            {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
        )
        await self.cdp(
            "Input.dispatchKeyEvent",
            {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
        )
        await asyncio.sleep(1.5)
        started = await self._submit_started()
        if await self._stream_started(started):
            return {"ok": True, "mode": "enterKeyFallback"}

        started = await self._submit_started()
        if await self._stream_started(started):
            return {"ok": True, "mode": "postBridgeProbe", "started": started}
        return {"ok": False, "mode": "submitExhausted", "started": started}
