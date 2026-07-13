"""Chrome page lifecycle owned by wave leases.

[INPUT]
- Lease pageId bindings from the wave state.
- Local Chrome DevTools HTTP endpoint on the dedicated E2E port.

[OUTPUT]
- bind/unbind metadata and best-effort page close on release/reap.

[POS]
The orchestrator owns page cleanup, while Chrome DevTools MCP still owns all
real UI actions. The HTTP endpoint is used only for deterministic teardown.
"""

from __future__ import annotations

import os
import json
import urllib.error
import urllib.request
from typing import TypedDict

from wave_orchestrator.types import LeaseRecord, OrchestratorState


class BrowserCleanupAttempt(TypedDict):
    pageId: str
    ok: bool
    detail: str


def _chrome_port() -> int:
    raw = os.environ.get("MYRM_CHROME_E2E_PORT", "9333").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 9333


def bind_browser(
    lease: LeaseRecord,
    *,
    page_id: str,
    page_url: str = "",
    context_id: str = "",
) -> LeaseRecord:
    page = page_id.strip()
    if not page:
        raise RuntimeError("BROWSER_BIND_DENIED: pageId is required")
    lease["pageId"] = page
    if page_url.strip():
        lease["pageUrl"] = page_url.strip()
    if context_id.strip():
        lease["contextId"] = context_id.strip()
    return lease


def unbind_browser(lease: LeaseRecord) -> LeaseRecord:
    lease.pop("pageId", None)
    lease.pop("pageUrl", None)
    lease.pop("contextId", None)
    return lease


def _close_target(target_id: str, page_id: str, detail: str = "") -> BrowserCleanupAttempt:
    url = f"http://127.0.0.1:{_chrome_port()}/json/close/{target_id}"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            response.read()
            return {"pageId": page_id, "ok": response.status in {200, 404}, "detail": detail or f"HTTP {response.status}"}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {"pageId": page_id, "ok": True, "detail": f"already closed (HTTP 404){detail}"}
        return {"pageId": page_id, "ok": False, "detail": f"HTTP {exc.code}{detail}"}
    except (OSError, urllib.error.URLError) as exc:
        return {"pageId": page_id, "ok": False, "detail": str(exc)}


def _close_page(page_id: str, page_url: str = "") -> BrowserCleanupAttempt:
    page = page_id.strip()
    if not page:
        return {"pageId": page_id, "ok": False, "detail": "empty pageId"}
    direct = _close_target(page, page)
    if (direct["ok"] and "HTTP 404" not in direct["detail"]) or not page_url.strip():
        return direct
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{_chrome_port()}/json/list", timeout=3) as response:
            targets = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return direct
    if not isinstance(targets, list):
        return direct
    for target in targets:
        if not isinstance(target, dict) or target.get("url") != page_url.strip():
            continue
        target_id = target.get("id")
        if isinstance(target_id, str) and target_id:
            return _close_target(target_id, page, " via pageUrl")
    return direct


def cleanup_lease_browser(lease: LeaseRecord) -> list[BrowserCleanupAttempt]:
    page_id = str(lease.get("pageId", "")).strip()
    if not page_id:
        return []
    attempt = _close_page(page_id, str(lease.get("pageUrl", "")))
    if attempt["ok"]:
        unbind_browser(lease)
    return [attempt]


def cleanup_expired_browser(state: OrchestratorState) -> bool:
    changed = False
    for lease in state["leases"]:
        if lease["status"] not in {"expired", "released"} or not lease.get("pageId"):
            continue
        cleanup_lease_browser(lease)
        changed = True
    return changed
