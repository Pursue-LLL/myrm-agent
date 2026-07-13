#!/usr/bin/env python3
"""CDP client hydration warmup — compile Turbopack client chunks before MCP E2E."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Protocol

from cdp_transient_targets import register_target, unregister_target
from cdp_write_guard import assert_cdp_write_allowed

_HYDRATED_EXPRESSION = """
(() => {
  const layout = document.querySelector('[data-testid="app-layout"]');
  if (!layout) {
    const shellSkeleton = document.querySelector('[data-testid="app-shell-skeleton"]');
    if (shellSkeleton) return false;
    if (document.readyState !== 'complete') return false;
    return false;
  }
  const listSkeleton = document.querySelector('[aria-label="Loading messages"]');
  if (listSkeleton) return false;
  return !!document.querySelector('[data-chat-input]');
})()
""".strip()

_RESET_CHAT_EXPRESSION = """
(() => {
  if (document.querySelector('[data-chat-input]')) {
    return { ok: true, mode: 'already' };
  }
  const newBtn = Array.from(document.querySelectorAll('aside button')).find((b) => {
    const text = (b.textContent || '').trim();
    return text.includes('新对话') || text.includes('New chat');
  });
  if (newBtn) {
    newBtn.click();
    return { ok: true, mode: 'new-chat' };
  }
  return { ok: false, mode: 'no-button' };
})()
""".strip()


class CdpSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


def _fetch_json(url: str, *, timeout: float = 10.0, method: str = "GET") -> object:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _create_target(cdp_port: int, page_url: str) -> dict[str, object]:
    assert_cdp_write_allowed(operation="json/new")
    encoded = urllib.request.quote(page_url, safe="")
    data = _fetch_json(
        f"http://127.0.0.1:{cdp_port}/json/new?{encoded}",
        timeout=15.0,
        method="PUT",
    )
    if not isinstance(data, dict):
        raise RuntimeError("CDP /json/new returned unexpected payload")
    ws_url = data.get("webSocketDebuggerUrl")
    if not isinstance(ws_url, str) or not ws_url.startswith("ws://"):
        raise RuntimeError("CDP target missing webSocketDebuggerUrl")
    return data


async def _cdp_request(
    ws: CdpSocket,
    msg_id: int,
    method: str,
    params: dict[str, object] | None = None,
    *,
    deadline: float,
) -> dict[str, object]:
    payload: dict[str, object] = {"id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    await ws.send(json.dumps(payload))

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"CDP request timed out: {method}")
        raw = await asyncio.wait_for(ws.recv(), timeout=min(3.0, remaining))
        message = json.loads(raw)
        if not isinstance(message, dict):
            continue
        if message.get("id") != msg_id:
            continue
        if "error" in message:
            err = message["error"]
            detail = err.get("message", err) if isinstance(err, dict) else err
            raise RuntimeError(f"CDP {method} failed: {detail}")
        return message


async def _wait_for_hydration(ws_url: str, page_url: str, *, timeout_sec: float, poll_ms: int) -> bool:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError(
            "websockets package required — run: cd myrm-agent-server && uv sync"
        ) from exc

    deadline = time.monotonic() + timeout_sec

    async with websockets.connect(ws_url, open_timeout=10, max_size=8 * 1024 * 1024) as ws:
        msg_id = 0

        async def next_id() -> int:
            nonlocal msg_id
            msg_id += 1
            return msg_id

        await _cdp_request(ws, await next_id(), "Runtime.enable", deadline=deadline)
        await _cdp_request(ws, await next_id(), "Page.enable", deadline=deadline)
        await _cdp_request(
            ws,
            await next_id(),
            "Page.navigate",
            {"url": page_url},
            deadline=deadline,
        )

        poll_count = 0
        while time.monotonic() < deadline:
            poll_count += 1
            try:
                result = await _cdp_request(
                    ws,
                    await next_id(),
                    "Runtime.evaluate",
                    {"expression": _HYDRATED_EXPRESSION, "returnByValue": True},
                    deadline=deadline,
                )
            except (TimeoutError, RuntimeError):
                await asyncio.sleep(poll_ms / 1000.0)
                continue

            outer_result = result.get("result")
            inner_result = outer_result.get("result") if isinstance(outer_result, dict) else None
            value = inner_result.get("value") if isinstance(inner_result, dict) else None
            if value is True:
                return True
            if poll_count % 10 == 0:
                try:
                    await _cdp_request(
                        ws,
                        await next_id(),
                        "Runtime.evaluate",
                        {"expression": _RESET_CHAT_EXPRESSION, "returnByValue": True},
                        deadline=deadline,
                    )
                except (TimeoutError, RuntimeError):
                    pass
            await asyncio.sleep(poll_ms / 1000.0)

    return False


async def _close_target(cdp_port: int, target_id: str) -> bool:
    try:
        import websockets
    except ImportError:
        return False

    version = _fetch_json(f"http://127.0.0.1:{cdp_port}/json/version", timeout=5.0)
    if not isinstance(version, dict):
        return False
    browser_ws = version.get("webSocketDebuggerUrl")
    if not isinstance(browser_ws, str):
        return False

    try:
        async with websockets.connect(browser_ws, open_timeout=5) as ws:
            await ws.send(
                json.dumps(
                    {"id": 1, "method": "Target.closeTarget", "params": {"targetId": target_id}}
                )
            )
            raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            response = json.loads(raw)
            result = response.get("result") if isinstance(response, dict) else None
            if isinstance(result, dict) and result.get("success") is True:
                return True
    except (OSError, asyncio.TimeoutError, json.JSONDecodeError):
        pass

    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{cdp_port}/json/close/{target_id}",
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=3.0) as response:
            response.read()
        return True
    except urllib.error.HTTPError as exc:
        return exc.code == 404
    except (OSError, urllib.error.URLError):
        return False


async def _run_warmup(
    *,
    cdp_port: int,
    page_url: str,
    timeout_sec: float,
    poll_ms: int,
) -> None:
    last_error = "unknown"
    for attempt in range(1, 3):
        target = _create_target(cdp_port, page_url)
        ws_url = str(target["webSocketDebuggerUrl"])
        target_id = target.get("id")
        if not isinstance(target_id, str) or not target_id:
            raise RuntimeError("CDP target missing id")
        register_target(target_id, page_url)
        ready = False
        closed = False
        try:
            ready = await _wait_for_hydration(
                ws_url, page_url, timeout_sec=timeout_sec, poll_ms=poll_ms
            )
            if not ready:
                last_error = f"hydration timeout after {timeout_sec:.0f}s (attempt {attempt})"
        except Exception as exc:
            last_error = f"{exc} (attempt {attempt})"
        finally:
            try:
                closed = await _close_target(cdp_port, target_id)
            finally:
                if closed:
                    unregister_target(target_id)
        if ready and closed:
            return
        if ready:
            last_error = f"hydrated target {target_id} could not be closed"
        if attempt < 2:
            await asyncio.sleep(1.0)

    raise RuntimeError(last_error)


def main() -> int:
    parser = argparse.ArgumentParser(description="Warm Next.js client bundles via CDP.")
    parser.add_argument("--cdp-port", type=int, default=9333)
    parser.add_argument("--url", default="http://127.0.0.1:3000/")
    parser.add_argument("--timeout-sec", type=float, default=120.0)
    parser.add_argument("--poll-ms", type=int, default=500)
    args = parser.parse_args()

    os.environ.setdefault("MYRM_CDP_WARMUP", "1")

    try:
        asyncio.run(
            _run_warmup(
                cdp_port=args.cdp_port,
                page_url=args.url,
                timeout_sec=args.timeout_sec,
                poll_ms=args.poll_ms,
            )
        )
    except urllib.error.URLError as exc:
        print(f"CLIENT_WARMUP_FAIL: CDP unreachable on :{args.cdp_port} — {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"CLIENT_WARMUP_FAIL: {exc}", file=sys.stderr)
        return 1

    print("CLIENT_WARMUP_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
