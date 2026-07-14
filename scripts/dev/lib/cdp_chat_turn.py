"""Chat turn observation and completion workflow."""

from __future__ import annotations

import asyncio
import json
import time

from cdp_chat_submit import CdpChatSubmit
from cdp_chat_support import chat_id_from_path, chat_messages_have_ok, chat_user_message_count
from cdp_chat_support import BRIDGE_TURN_SNAPSHOT_JS
from e2e_wave_ledger import maybe_register_e2e_chat


class CdpChatTurn(CdpChatSubmit):
    async def main_state(
        self,
        prompt: str,
        *,
        recv_timeout: float = 90.0,
    ) -> dict[str, object]:
        result = await self.evaluate(
            f"""( () => {{
              const main = document.querySelector('main');
              const text = main?.innerText || '';
              const userMsgs = main?.querySelectorAll('[data-message-id]')?.length || 0;
              const assistantNodes = Array.from(
                main?.querySelectorAll('[data-test-id="assistant-message"]') || [],
              );
              const assistantText = assistantNodes.map((el) => el.innerText || '').join('\\n');
              const sending = !!main?.querySelector('button[aria-label="Stop"]');
              const hasUserPrompt = userMsgs > 0 || text.includes({json.dumps(prompt)});
              const okInAssistant = /\\bOK\\b/i.test(assistantText);
              const okInMain =
                hasUserPrompt &&
                (okInAssistant ||
                  /\\bOK\\b/i.test(text) ||
                  /^\\s*OK\\s*$/m.test(text) ||
                  (text.includes('OK') && !sending));
              return {{
                url: location.href,
                path: location.pathname,
                bridgeChatId: window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.chatId ?? null,
                userMsgs,
                sending,
                hasUserPrompt,
                okInMain,
                okInAssistant,
                sample: text.slice(0, 500),
                assistantSample: assistantText.slice(0, 300),
              }};
            }})()""",
            await_promise=False,
            recv_timeout=recv_timeout,
        )
        return result if isinstance(result, dict) else {"hasUserPrompt": False, "okInMain": False}

    async def wait_stream_started(self, prompt: str, *, timeout_sec: float = 180.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            try:
                last = await self.main_state(prompt)
            except TimeoutError:
                await asyncio.sleep(1)
                continue
            if (
                last.get("sending")
                or last.get("hasUserPrompt")
                or int(last.get("userMsgs") or 0) > 0
            ):
                return last
            chat_id = await self.resolve_chat_id(
                path=str(last.get("path") or ""),
                hint=str(last.get("bridgeChatId") or "").strip() or None,
            )
            if chat_id and chat_user_message_count(chat_id) > 0:
                last["chatId"] = chat_id
                last["okViaApi"] = True
                return last
            if chat_id and chat_messages_have_ok(chat_id, min_user_count=1):
                return last
            await asyncio.sleep(0.75)
        raise TimeoutError(f"UI send did not start stream: {last}")

    async def _bridge_turn_snapshot(self) -> dict[str, object] | None:
        try:
            result = await self.evaluate(BRIDGE_TURN_SNAPSHOT_JS, await_promise=False, recv_timeout=8.0)
        except RuntimeError:
            return None
        return result if isinstance(result, dict) else None

    async def _finish_if_api_ok(
        self,
        chat_id: str,
        prompt: str,
        *,
        min_user_msgs: int,
    ) -> dict[str, object] | None:
        try:
            if not chat_messages_have_ok(chat_id, min_user_count=min_user_msgs):
                return None
        except OSError:
            return None
        try:
            last = await self.main_state(prompt, recv_timeout=8.0)
        except RuntimeError:
            last = {}
        last["chatId"] = chat_id
        last["okViaApi"] = True
        last["okViaBridge"] = False
        maybe_register_e2e_chat(chat_id)
        return last

    async def wait_turn_done(
        self,
        prompt: str,
        *,
        chat_id_hint: str | None = None,
        min_user_msgs: int = 1,
        timeout_sec: float = 180.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}

        def _finish(chat_id: str, payload: dict[str, object]) -> dict[str, object]:
            payload["chatId"] = chat_id
            payload["okViaApi"] = payload.get("okViaApi", True)
            maybe_register_e2e_chat(chat_id)
            return payload

        if chat_id_hint:
            api_deadline = min(deadline, time.monotonic() + min(timeout_sec, 120.0))
            while time.monotonic() < api_deadline:
                finished = await self._finish_if_api_ok(
                    chat_id_hint, prompt, min_user_msgs=min_user_msgs
                )
                if finished is not None:
                    return finished
                bridge = await self._bridge_turn_snapshot()
                if (
                    isinstance(bridge, dict)
                    and int(bridge.get("userCount") or 0) >= min_user_msgs
                    and bridge.get("hasOk")
                    and not bridge.get("isStreaming")
                ):
                    return _finish(
                        chat_id_hint,
                        {
                            **bridge,
                            "okViaBridge": True,
                            "okViaApi": False,
                        },
                    )
                await asyncio.sleep(1.5)

        while time.monotonic() < deadline:
            bridge = await self._bridge_turn_snapshot()
            if isinstance(bridge, dict):
                last = bridge
                chat_id = str(bridge.get("chatId") or "").strip() or chat_id_hint
                if (
                    chat_id
                    and int(bridge.get("userCount") or 0) >= min_user_msgs
                    and bridge.get("hasOk")
                    and not bridge.get("isStreaming")
                ):
                    return _finish(chat_id, {**bridge, "okViaBridge": True, "okViaApi": False})

            chat_id = chat_id_hint
            if not chat_id:
                try:
                    probe = await self.main_state(prompt, recv_timeout=8.0)
                    if isinstance(probe, dict):
                        last = probe
                        chat_id = await self.resolve_chat_id(
                            path=str(probe.get("path") or ""),
                            hint=str(probe.get("bridgeChatId") or "").strip() or None,
                        )
                except RuntimeError as exc:
                    message = str(exc)
                    if any(
                        token in message
                        for token in ("Target closed", "No page found", "detached Frame")
                    ):
                        await asyncio.sleep(1.5)
                        continue
                    raise
            if not chat_id:
                chat_id = await self.bridge_chat_id()
            if chat_id:
                finished = await self._finish_if_api_ok(
                    chat_id, prompt, min_user_msgs=min_user_msgs
                )
                if finished is not None:
                    return finished
            try:
                last = await self.main_state(prompt, recv_timeout=8.0)
            except RuntimeError as exc:
                message = str(exc)
                if any(
                    token in message
                    for token in ("Target closed", "No page found", "detached Frame")
                ):
                    await asyncio.sleep(1.5)
                    continue
                raise
            chat_id = await self.resolve_chat_id(
                path=str(last.get("path") or ""),
                hint=str(last.get("bridgeChatId") or "").strip() or chat_id_hint,
            )
            if last.get("sending"):
                await asyncio.sleep(1)
                continue
            if chat_id:
                finished = await self._finish_if_api_ok(
                    chat_id, prompt, min_user_msgs=min_user_msgs
                )
                if finished is not None:
                    return finished
            if last.get("hasUserPrompt") and last.get("okInMain"):
                if chat_id:
                    maybe_register_e2e_chat(chat_id)
                    last["chatId"] = chat_id
                return last
            await asyncio.sleep(1.5)
        raise TimeoutError(f"Timed out waiting for assistant OK: {last}")

    async def wait_input_empty(self, *, timeout_sec: float = 60.0) -> None:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            bridge = await self._bridge_turn_snapshot()
            if (
                isinstance(bridge, dict)
                and not bridge.get("isStreaming")
                and bridge.get("hasOk")
            ):
                await self.evaluate(
                    """(() => {
                      window.__MYRM_E2E_CHAT__?.setInputMessage?.('');
                      return { ok: true };
                    })()""",
                    await_promise=False,
                    recv_timeout=8.0,
                )
                return
            probe = await self.send_state()
            last = probe
            if not probe.get("sendDisabled") and int(probe.get("inputLen") or 0) == 0:
                return
            await asyncio.sleep(1)
        raise TimeoutError(f"Chat input not ready for send: {last}")

    async def send_message(self, text: str, prompt_for_wait: str) -> dict[str, object]:
        await self.dismiss_modals()
        await self.wait_dev_bridge()
        await self._ensure_send_ready()
        fill = await self.fill_input(text)
        if not fill.get("ok"):
            raise RuntimeError(f"UI fill failed: {fill}")
        await self.evaluate(
            """(() => {
              void window.__MYRM_E2E_CHAT__?.ensureChatSession?.();
              return { ok: true };
            })()""",
            await_promise=False,
            recv_timeout=15.0,
        )
        submit = await self.submit()
        if not submit.get("ok"):
            probe = await self.send_state()
            chat_id = await self.bridge_chat_id()
            if chat_id and chat_user_message_count(chat_id) > 0:
                submit = {**submit, "ok": True, "mode": "apiConfirmedWithoutDom", "chatId": chat_id}
            elif int(probe.get("inputLen") or 0) > 0:
                raise RuntimeError(f"UI submit failed: {submit} fill={fill}")
            else:
                submit = {**submit, "ok": True, "mode": "clearedWithoutStreamProbe"}
        started: dict[str, object]
        try:
            started = await asyncio.wait_for(
                self.wait_stream_started(prompt_for_wait),
                timeout=45.0,
            )
        except TimeoutError:
            started = await self.main_state(prompt_for_wait)
            started["streamProbe"] = "deferred_to_wait_turn_done"
        chat_id = await self.bridge_chat_id()
        if chat_id:
            started["chatId"] = chat_id
        return {"fill": fill, "submit": submit, "started": started}

