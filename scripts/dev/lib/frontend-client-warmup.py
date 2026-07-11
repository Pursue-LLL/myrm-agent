#!/usr/bin/env python3
"""CDP client hydration warmup — prove Turbopack client chunks are compiled before MCP E2E."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def _fetch_json(url: str, *, timeout: float = 10.0, method: str = "GET") -> Any:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _create_target(cdp_port: int, page_url: str) -> dict[str, Any]:
    encoded = urllib.request.quote(page_url, safe="")
    # Chrome 131+ rejects GET on /json/new (405); PUT is the supported method.
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


async def _wait_for_app_layout(ws_url: str, *, timeout_sec: float, poll_ms: int) -> bool:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError(
            "websockets package required — run: cd myrm-agent-server && uv sync"
        ) from exc

    expression = 'Boolean(document.querySelector(\'[data-testid="app-layout"]\'))'
    deadline = time.monotonic() + timeout_sec

    async with websockets.connect(ws_url, open_timeout=10, max_size=8 * 1024 * 1024) as ws:
        msg_id = 0

        async def send(method: str, params: dict[str, Any] | None = None) -> None:
            nonlocal msg_id
            msg_id += 1
            payload: dict[str, Any] = {"id": msg_id, "method": method}
            if params is not None:
                payload["params"] = params
            await ws.send(json.dumps(payload))

        await send("Runtime.enable")
        await send("Page.enable")

        while time.monotonic() < deadline:
            msg_id += 1
            await ws.send(
                json.dumps(
                    {
                        "id": msg_id,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": expression,
                            "returnByValue": True,
                        },
                    }
                )
            )

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(2.0, remaining))
                except asyncio.TimeoutError:
                    break
                message = json.loads(raw)
                if message.get("id") != msg_id:
                    continue
                result = message.get("result", {})
                value = result.get("result", {}).get("value")
                if value is True:
                    return True
                break

            await asyncio.sleep(poll_ms / 1000.0)

    return False


async def _run_warmup(*, cdp_port: int, page_url: str, timeout_sec: float, poll_ms: int) -> None:
    target = _create_target(cdp_port, page_url)
    ws_url = str(target["webSocketDebuggerUrl"])
    target_id = target.get("id")
    try:
        ready = await _wait_for_app_layout(ws_url, timeout_sec=timeout_sec, poll_ms=poll_ms)
        if not ready:
            raise RuntimeError(
                f"client hydration timeout after {timeout_sec:.0f}s — app-layout not ready"
            )
    finally:
        if isinstance(target_id, str) and target_id:
            try:
                await _close_target(cdp_port, target_id)
            except Exception:
                pass


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Warm Next.js client bundles via CDP.")
    parser.add_argument("--cdp-port", type=int, default=9333)
    parser.add_argument("--url", default="http://127.0.0.1:3000/")
    parser.add_argument("--timeout-sec", type=float, default=90.0)
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
