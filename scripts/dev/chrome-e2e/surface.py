#!/usr/bin/env python3
"""Agent Operating Surface (AOS) — dedicated OFFSCREEN-NORMAL window for Myrm E2E Chrome.

Offscreen-normal (never minimized) keeps rAF running so Next.js hydration never
freezes and the test layer never needs focus-stealing activation (§26.21/§26.25).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol


class CdpSocket(Protocol):
    async def send(self, message: str) -> None: ...

    async def recv(self) -> str | bytes: ...


def _state_dir() -> Path:
    return Path(
        os.environ.get("MYRM_DEV_STATE_DIR", Path.home() / ".local/state/myrm-dev")
    )


def _registry_path() -> Path:
    return _state_dir() / "chrome-e2e-agent-window.json"


def _fetch_json(url: str, *, timeout: float = 10.0) -> object:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_registry() -> dict[str, object]:
    path = _registry_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_registry(data: dict[str, object]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"CDP request timed out: {method}")
        raw = await asyncio.wait_for(ws.recv(), timeout=min(10.0, remaining))
        message = json.loads(raw)
        if not isinstance(message, dict):
            continue
        if message.get("id") != msg_id:
            continue
        if "error" in message:
            err = message["error"]
            detail = err.get("message", err) if isinstance(err, dict) else err
            raise RuntimeError(f"CDP {method} failed: {detail}")
        result = message.get("result")
        return result if isinstance(result, dict) else {}
    raise TimeoutError(f"CDP request timed out: {method}")


async def _park_window_offscreen(
    ws: CdpSocket, msg_id: int, window_id: int, *, deadline: float
) -> None:
    """Park a window OFFSCREEN-NORMAL (§26.21/§26.23 focus-theft fix).

    `windowState:'minimized'` pauses requestAnimationFrame, which stalls
    Next.js 16's $RV Suspense flush — rendering freezes and probes report
    `__windowHidden`. An offscreen normal window keeps
    `visibilityState==='visible'` so rendering never stops while staying away
    from the user's desktop. This mirrors `cdp-plane.ts::parkTargetWindowOffscreen`.
    """
    await _cdp_request(
        ws,
        msg_id,
        "Browser.setWindowBounds",
        {
            "windowId": window_id,
            "bounds": {
                "windowState": "normal",
                "left": -24000,
                "top": -24000,
                "width": 1400,
                "height": 900,
            },
        },
        deadline=deadline,
    )


async def _window_for_target(
    ws: CdpSocket, msg_id: int, target_id: str, *, deadline: float
) -> int | None:
    result = await _cdp_request(
        ws,
        msg_id,
        "Browser.getWindowForTarget",
        {"targetId": target_id},
        deadline=deadline,
    )
    window_id = result.get("windowId")
    return window_id if isinstance(window_id, int) else None


def _default_context_page_targets(targets: object) -> list[dict[str, object]]:
    """Filter CDP ``Target.getTargets`` data to Chrome's default context.

    Browser Orchestrator puts each test session in a dedicated context. AOS is
    persistent, so adopting one of those pages would steal peer ownership and
    keep its context alive after the session seals. The HTTP ``/json/list``
    endpoint omits ``browserContextId``; callers must pass browser-level CDP
    ``Target.getTargets`` data so this ownership boundary is authoritative.
    """
    if not isinstance(targets, list):
        return []
    result: list[dict[str, object]] = []
    for entry in targets:
        if not isinstance(entry, dict) or entry.get("type") != "page":
            continue
        context_id = entry.get("browserContextId")
        if isinstance(context_id, str) and context_id.strip():
            continue
        result.append(entry)
    return result


async def _list_default_context_page_targets(
    ws: CdpSocket, *, msg_id: int, deadline: float
) -> list[dict[str, object]]:
    result = await _cdp_request(
        ws,
        msg_id,
        "Target.getTargets",
        deadline=deadline,
    )
    return _default_context_page_targets(result.get("targetInfos"))


async def _adopt_live_anchor(
    ws: CdpSocket,
    *,
    deadline: float,
) -> tuple[str, int]:
    """Pick the first live page target as the AOS anchor and park it offscreen.

    Chrome recycles `Target.createTarget(newWindow=true)` blank windows and their
    windowIds are not reliably addressable afterwards (§26.25). Adopting a real
    page window — the same window `_park_all_page_windows_offscreen` parks —
    gives us a stable, addressable anchor that stays valid between ensure runs.
    """
    for entry in await _list_default_context_page_targets(
        ws, msg_id=4, deadline=deadline
    ):
        target_id = entry.get("targetId")
        if not isinstance(target_id, str) or not target_id:
            continue
        window_id = await _window_for_target(ws, 5, target_id, deadline=deadline)
        if isinstance(window_id, int):
            await _park_window_offscreen(ws, 6, window_id, deadline=deadline)
            return target_id, window_id
    # No live page yet — fall back to creating a dedicated blank window.
    return await _create_agent_window(ws, deadline=deadline)


async def _create_agent_window(ws: CdpSocket, *, deadline: float) -> tuple[str, int]:
    msg_id = 1
    result = await _cdp_request(
        ws,
        msg_id,
        "Target.createTarget",
        {"url": "about:blank", "newWindow": True, "background": True},
        deadline=deadline,
    )
    target_id = result.get("targetId")
    if not isinstance(target_id, str) or not target_id:
        raise RuntimeError("Target.createTarget missing targetId")
    msg_id += 1
    window_id = await _window_for_target(ws, msg_id, target_id, deadline=deadline)
    if window_id is None:
        raise RuntimeError("Browser.getWindowForTarget missing windowId")
    msg_id += 1
    try:
        await _park_window_offscreen(ws, msg_id, window_id, deadline=deadline)
    except (TimeoutError, RuntimeError, asyncio.TimeoutError):
        # Best-effort: a freshly created new-window target may not yet expose a
        # valid windowId to Browser.setWindowBounds (§26.25). The anchor is
        # still recorded; re-parking happens on the next ensure pass.
        pass
    return target_id, window_id


async def _park_all_page_windows_offscreen(
    ws: CdpSocket, *, deadline: float
) -> None:
    targets = await _list_default_context_page_targets(
        ws, msg_id=9, deadline=deadline
    )
    msg_id = 10
    seen: set[int] = set()
    for entry in targets:
        target_id = entry.get("targetId")
        if not isinstance(target_id, str) or not target_id:
            continue
        try:
            window_id = await _window_for_target(
                ws, msg_id, target_id, deadline=deadline
            )
            msg_id += 1
            if window_id is None or window_id in seen:
                continue
            seen.add(window_id)
            await _park_window_offscreen(ws, msg_id, window_id, deadline=deadline)
            msg_id += 1
        except (TimeoutError, RuntimeError, asyncio.TimeoutError):
            continue


async def ensure_agent_surface(*, cdp_port: int) -> dict[str, object]:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError(
            "websockets required — cd myrm-agent-server && uv sync"
        ) from exc

    version = _fetch_json(f"http://127.0.0.1:{cdp_port}/json/version", timeout=5.0)
    if not isinstance(version, dict):
        raise RuntimeError("CDP /json/version unexpected payload")
    browser_ws = version.get("webSocketDebuggerUrl")
    if not isinstance(browser_ws, str) or not browser_ws.startswith("ws://"):
        raise RuntimeError("CDP browser missing webSocketDebuggerUrl")

    registry = _load_registry()
    deadline = time.monotonic() + 20.0

    async with websockets.connect(
        browser_ws, open_timeout=10, max_size=4 * 1024 * 1024
    ) as ws:
        anchor_target = registry.get("anchorTargetId")
        window_id = registry.get("windowId")
        valid = False
        if (
            isinstance(anchor_target, str)
            and anchor_target
            and isinstance(window_id, int)
        ):
            try:
                current = await _window_for_target(
                    ws, 1, anchor_target, deadline=deadline
                )
                default_targets = await _list_default_context_page_targets(
                    ws, msg_id=2, deadline=deadline
                )
                valid = current == window_id and any(
                    entry.get("targetId") == anchor_target
                    for entry in default_targets
                )
            except (TimeoutError, RuntimeError, asyncio.TimeoutError):
                valid = False

        if not valid:
            # Reuse a live page window as the anchor instead of creating a new
            # one: Target.createTarget(newWindow=true) targets are recycled by
            # Chrome and their windowId is not reliably addressable (§26.25).
            anchor_target, window_id = await _adopt_live_anchor(
                ws, deadline=deadline
            )
            registry = {
                "windowId": window_id,
                "anchorTargetId": anchor_target,
                "updatedAt": int(time.time()),
            }
            _save_registry(registry)
        else:
            try:
                await _park_window_offscreen(ws, 2, window_id, deadline=deadline)
            except (TimeoutError, RuntimeError, asyncio.TimeoutError):
                # anchor window was closed since the registry was written —
                # adopt a live window so the offscreen surface stays intact.
                anchor_target, window_id = await _adopt_live_anchor(
                    ws, deadline=deadline
                )
                registry = {
                    "windowId": window_id,
                    "anchorTargetId": anchor_target,
                    "updatedAt": int(time.time()),
                }
                _save_registry(registry)

        await _park_all_page_windows_offscreen(ws, deadline=deadline)

    return registry


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Myrm E2E Chrome Agent Operating Surface"
    )
    parser.add_argument("command", choices=["ensure", "registry"])
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=int(os.environ.get("MYRM_CHROME_E2E_PORT", "9333")),
    )
    args = parser.parse_args()

    if args.command == "registry":
        print(json.dumps(_load_registry(), indent=2))
        return 0

    try:
        registry = asyncio.run(ensure_agent_surface(cdp_port=args.cdp_port))
    except (
        OSError,
        urllib.error.URLError,
        RuntimeError,
        TimeoutError,
        asyncio.TimeoutError,
    ) as exc:
        print(f"CHROME_E2E_SURFACE_WARN: {exc}", file=os.sys.stderr)
        return 0

    window_id = registry.get("windowId")
    print(f"CHROME_E2E_SURFACE_OK windowId={window_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
