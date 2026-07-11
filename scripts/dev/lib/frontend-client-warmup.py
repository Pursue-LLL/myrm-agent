#!/usr/bin/env python3
"""CDP client hydration warmup — compile Turbopack client chunks before MCP E2E."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

_HYDRATED_EXPRESSION = """
(() => {
  const layout = document.querySelector('[data-testid="app-layout"]');
  if (layout) return true;
  const skeleton = document.querySelector('[data-testid="app-shell-skeleton"]');
  if (skeleton) return false;
  if (document.readyState !== 'complete') return false;
  const text = (document.body && document.body.innerText) ? document.body.innerText.trim() : '';
  return text.length > 20;
})()
""".strip()


def _fetch_json(url: str, *, timeout: float = 10.0, method: str = "GET") -> Any:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _create_target(cdp_port: int, page_url: str) -> dict[str, Any]:
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
    ws: Any,
    msg_id: int,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    deadline: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    await ws.send(json.dumps(payload))

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"CDP request timed out: {method}")
        raw = await asyncio.wait_for(ws.recv(), timeout=min(3.0, remaining))
        message = json.loads(raw)
        if message.get("id") != msg_id:
            continue
        if "error" in message:
            err = message["error"]
            raise RuntimeError(f"CDP {method} failed: {err.get('message', err)}")
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

        while time.monotonic() < deadline:
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

            value = result.get("result", {}).get("result", {}).get("value")
            if value is True:
                return True
            await asyncio.sleep(poll_ms / 1000.0)

    return False


async def _close_target(cdp_port: int, target_id: str) -> None:
    try:
        import websockets
    except ImportError:
        return

    version = _fetch_json(f"http://127.0.0.1:{cdp_port}/json/version", timeout=5.0)
    browser_ws = version.get("webSocketDebuggerUrl")
    if not isinstance(browser_ws, str):
        return

    async with websockets.connect(browser_ws, open_timeout=5) as ws:
        await ws.send(
            json.dumps({"id": 1, "method": "Target.closeTarget", "params": {"targetId": target_id}})
        )
        try:
            await asyncio.wait_for(ws.recv(), timeout=2.0)
        except asyncio.TimeoutError:
            pass


async def _run_warmup(*, cdp_port: int, page_url: str, timeout_sec: float, poll_ms: int) -> None:
    last_error = "unknown"
    for attempt in range(1, 3):
        target = _create_target(cdp_port, page_url)
        ws_url = str(target["webSocketDebuggerUrl"])
        target_id = target.get("id")
        try:
            ready = await _wait_for_hydration(
                ws_url, page_url, timeout_sec=timeout_sec, poll_ms=poll_ms
            )
            if ready:
                return
            last_error = f"hydration timeout after {timeout_sec:.0f}s (attempt {attempt})"
        except Exception as exc:
            last_error = f"{exc} (attempt {attempt})"
        finally:
            if isinstance(target_id, str) and target_id:
                try:
                    await _close_target(cdp_port, target_id)
                except Exception:
                    pass
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
