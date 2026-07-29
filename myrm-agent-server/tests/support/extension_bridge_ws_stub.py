"""Real WebSocket stub for Extension Bridge Chrome E2E (no MV3 sideload)."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlparse

import websockets

from tests.support.chrome_mcp_e2e import http_json

_EXTENSION_CAPABILITIES = [
    "navigate_url",
    "list_tabs",
    "attach_debugger",
    "detach_debugger",
]


def _api_url_to_ws_url(api_url: str, token: str) -> str:
    parsed = urlparse(api_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    query = f"?token={token}" if token else ""
    return f"{scheme}://{host}:{port}/api/v1/ws/extension{query}"


async def _extension_stub_loop(ws_url: str, stop: threading.Event) -> None:
    headers = {"Origin": "chrome-extension://myrm-e2e-stub"}
    async with websockets.connect(ws_url, additional_headers=headers) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "version": "e2e-stub",
                    "browser": "Chrome",
                    "capabilities": list(_EXTENSION_CAPABILITIES),
                }
            )
        )
        while not stop.is_set():
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ping":
                await ws.send(json.dumps({"type": "pong"}))


def wait_extension_handshake_ready(
    api_url: str,
    *,
    timeout_sec: float = 15.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        status = http_json("GET", f"{api_url}/api/v1/extension/status")
        if not isinstance(status, dict):
            time.sleep(0.2)
            continue
        capabilities = status.get("capabilities")
        if (
            status.get("connected") is True
            and status.get("handshake_ready") is True
            and isinstance(capabilities, list)
            and set(_EXTENSION_CAPABILITIES).issubset(set(capabilities))
        ):
            return status
        time.sleep(0.2)
    raise TimeoutError(
        "Extension bridge did not reach connected+handshake_ready with four capabilities"
    )


@contextmanager
def hold_extension_bridge_session(api_url: str) -> Iterator[None]:
    """Keep a real extension WebSocket session open for Chrome UI E2E."""
    token = os.environ.get("EXTENSION_AUTH_TOKEN", "")
    ws_url = _api_url_to_ws_url(api_url, token)
    stop = threading.Event()
    loop = asyncio.new_event_loop()
    thread_error: list[BaseException] = []

    def _run() -> None:
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_extension_stub_loop(ws_url, stop))
        except BaseException as exc:  # noqa: BLE001 — propagate to test
            thread_error.append(exc)
        finally:
            loop.close()

    thread = threading.Thread(target=_run, name="extension-bridge-e2e-stub", daemon=True)
    thread.start()
    try:
        wait_extension_handshake_ready(api_url)
        if thread_error:
            raise thread_error[0]
        yield
    finally:
        stop.set()
        thread.join(timeout=5.0)
        try:
            http_json("POST", f"{api_url}/api/v1/extension/disconnect")
        except Exception:
            pass
