#!/usr/bin/env python3
"""Browser human-in-loop overlay for Myrm E2E Chrome (Dev Gate only)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.request

_HIL_OVERLAY_JS = """
(() => {
  const id = '__MYRM_E2E_HIL__';
  let el = document.getElementById(id);
  if (!el) {
    el = document.createElement('div');
    el.id = id;
    el.style.cssText = [
      'position:fixed', 'top:16px', 'left:50%', 'transform:translateX(-50%)',
      'z-index:2147483647', 'background:#111827', 'color:#f9fafb',
      'padding:12px 16px', 'border-radius:8px', 'font:14px/1.4 system-ui,sans-serif',
      'box-shadow:0 8px 24px rgba(0,0,0,.35)', 'max-width:min(90vw,560px)'
    ].join(';');
    document.documentElement.appendChild(el);
  }
  el.textContent = %s;
  return { ok: true, id };
})()
""".strip()


async def show_hil_prompt(*, cdp_port: int, target_id: str, message: str) -> None:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError("websockets required") from exc

    targets = json.loads(
        urllib.request.urlopen(
            f"http://127.0.0.1:{cdp_port}/json/list", timeout=5.0
        ).read().decode("utf-8")
    )
    ws_url = None
    if isinstance(targets, list):
        for entry in targets:
            if isinstance(entry, dict) and entry.get("id") == target_id:
                candidate = entry.get("webSocketDebuggerUrl")
                if isinstance(candidate, str):
                    ws_url = candidate
                    break
    if ws_url is None:
        raise RuntimeError(f"target {target_id} not found on :{cdp_port}")

    payload = _HIL_OVERLAY_JS % json.dumps(message)
    deadline = time.monotonic() + 15.0
    async with websockets.connect(ws_url, open_timeout=10) as ws:
        msg_id = 1
        await ws.send(
            json.dumps(
                {
                    "id": msg_id,
                    "method": "Runtime.evaluate",
                    "params": {"expression": payload, "returnByValue": True},
                }
            )
        )
        while time.monotonic() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = json.loads(raw)
            if isinstance(response, dict) and response.get("id") == msg_id:
                return


def main() -> int:
    parser = argparse.ArgumentParser(description="Show HIL overlay on E2E Chrome tab")
    parser.add_argument("--cdp-port", type=int, default=int(os.environ.get("MYRM_CHROME_E2E_PORT", "9333")))
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(
            show_hil_prompt(
                cdp_port=args.cdp_port,
                target_id=args.target_id,
                message=args.message,
            )
        )
    except (OSError, RuntimeError, asyncio.TimeoutError) as exc:
        print(f"CHROME_E2E_HIL_WARN: {exc}", file=os.sys.stderr)
        return 0
    print("CHROME_E2E_HIL_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
