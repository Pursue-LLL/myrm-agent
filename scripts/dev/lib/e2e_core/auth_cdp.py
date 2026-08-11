"""CDP cookie hydrate and authenticated probe for Auth State Provisioner (P0-C)."""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from typing import TypedDict

from e2e_browser_pool import resolve_chrome_port


class AuthCookieSeed(TypedDict, total=False):
    name: str
    value: str
    domain: str
    path: str
    secure: bool
    httpOnly: bool
    sameSite: str


def resolve_browser_websocket_url(*, cdp_port: int | None = None) -> str | None:
    port = resolve_chrome_port() if cdp_port is None else cdp_port
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    ws_url = payload.get("webSocketDebuggerUrl")
    return ws_url.strip() if isinstance(ws_url, str) and ws_url.strip() else None


async def _cdp_call(
    ws: object,
    msg_id: int,
    method: str,
    params: dict[str, object] | None = None,
    *,
    deadline: float,
) -> dict[str, object]:
    payload: dict[str, object] = {"id": msg_id, "method": method}
    if params is not None:
        payload["params"] = params
    await ws.send(json.dumps(payload))  # type: ignore[attr-defined]
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"CDP request timed out: {method}")
        raw = await asyncio.wait_for(ws.recv(), timeout=min(10.0, remaining))  # type: ignore[attr-defined]
        message = json.loads(raw)
        if not isinstance(message, dict) or message.get("id") != msg_id:
            continue
        if "error" in message:
            err = message["error"]
            detail = err.get("message", err) if isinstance(err, dict) else err
            raise RuntimeError(f"CDP {method} failed: {detail}")
        result = message.get("result")
        return result if isinstance(result, dict) else {}
    raise TimeoutError(f"CDP request timed out: {method}")


def _cookie_params(
    seed: AuthCookieSeed,
    *,
    origin: str,
) -> dict[str, object] | None:
    name = str(seed.get("name", "")).strip()
    value = str(seed.get("value", "")).strip()
    if not name:
        return None
    domain = str(seed.get("domain", "")).strip()
    path = str(seed.get("path", "/")).strip() or "/"
    params: dict[str, object] = {
        "name": name,
        "value": value,
        "path": path,
        "url": origin.rstrip("/") + path,
    }
    if domain:
        params["domain"] = domain
    if seed.get("secure") is True:
        params["secure"] = True
    if seed.get("httpOnly") is True:
        params["httpOnly"] = True
    same_site = seed.get("sameSite")
    if isinstance(same_site, str) and same_site.strip():
        params["sameSite"] = same_site.strip()
    return params


async def _hydrate_and_probe_async(
    *,
    browser_context_id: str,
    origin: str,
    cookies: list[AuthCookieSeed],
    probe_path: str,
    ws_url: str,
) -> bool:
    import websockets

    deadline = time.monotonic() + 30.0
    msg_id = 0
    async with websockets.connect(
        ws_url, open_timeout=10, max_size=4 * 1024 * 1024
    ) as ws:
        msg_id += 1
        created = await _cdp_call(
            ws,
            msg_id,
            "Target.createTarget",
            {
                "url": "about:blank",
                "browserContextId": browser_context_id,
                # Foreground create raises the Chrome app on macOS and steals
                # focus from the user's active app (§26.26 / R026). The probe is
                # a pure fetch — no visible rendering is needed.
                "background": True,
            },
            deadline=deadline,
        )
        target_id = str(created.get("targetId", "")).strip()
        if not target_id:
            return False
        msg_id += 1
        attached = await _cdp_call(
            ws,
            msg_id,
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
            deadline=deadline,
        )
        session_id = str(attached.get("sessionId", "")).strip()
        if not session_id:
            return False

        async def session_call(
            method: str, params: dict[str, object] | None = None
        ) -> dict[str, object]:
            nonlocal msg_id
            msg_id += 1
            envelope = {
                "id": msg_id,
                "method": method,
                "params": params or {},
                "sessionId": session_id,
            }
            await ws.send(json.dumps(envelope))
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                raw = await asyncio.wait_for(ws.recv(), timeout=min(10.0, remaining))
                message = json.loads(raw)
                if not isinstance(message, dict) or message.get("id") != msg_id:
                    continue
                if "error" in message:
                    err = message["error"]
                    detail = err.get("message", err) if isinstance(err, dict) else err
                    raise RuntimeError(f"CDP {method} failed: {detail}")
                result = message.get("result")
                return result if isinstance(result, dict) else {}
            raise TimeoutError(f"CDP session request timed out: {method}")

        await session_call("Network.enable")
        for seed in cookies:
            cookie = _cookie_params(seed, origin=origin)
            if cookie is None:
                continue
            await session_call("Network.setCookie", cookie)

        normalized_probe = (
            probe_path if probe_path.startswith("/") else f"/{probe_path}"
        )
        probe_url = origin.rstrip("/") + normalized_probe
        await session_call("Runtime.enable")
        probe_js = (
            "(() => fetch("
            f"{json.dumps(probe_url)}, "
            "{credentials:'include',redirect:'manual'}).then(r => r.status).catch(() => 0))()"
        )
        msg_id += 1
        await ws.send(
            json.dumps(
                {
                    "id": msg_id,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": probe_js,
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                    "sessionId": session_id,
                }
            )
        )
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            raw = await asyncio.wait_for(ws.recv(), timeout=min(10.0, remaining))
            message = json.loads(raw)
            if not isinstance(message, dict) or message.get("id") != msg_id:
                continue
            if "exceptionDetails" in message:
                return False
            payload = message.get("result", {}).get("result", {})
            status_code = payload.get("value") if isinstance(payload, dict) else None
            return isinstance(status_code, int) and 200 <= status_code < 400
    return False


def hydrate_and_probe_context(
    *,
    browser_context_id: str,
    origin: str,
    cookies: list[AuthCookieSeed],
    probe_path: str = "/",
    cdp_port: int | None = None,
) -> bool | None:
    """Hydrate cookies into an isolated browser context and probe origin auth.

    Returns True/False on observed probe result; None when CDP endpoint unreadable.
    """
    normalized_context = browser_context_id.strip()
    if not normalized_context:
        return False
    ws_url = resolve_browser_websocket_url(cdp_port=cdp_port)
    if ws_url is None:
        return None
    try:
        return asyncio.run(
            _hydrate_and_probe_async(
                browser_context_id=normalized_context,
                origin=origin.strip(),
                cookies=cookies,
                probe_path=probe_path.strip() or "/",
                ws_url=ws_url,
            )
        )
    except (ImportError, OSError, RuntimeError, TimeoutError, ValueError):
        return False


def cdp_auth_hydrate_enabled() -> bool:
    return os.environ.get("MYRM_E2E_AUTH_CDP_HYDRATE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
