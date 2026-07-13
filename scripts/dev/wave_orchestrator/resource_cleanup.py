"""HTTP cleanup drivers for wave resource ledger entries.

[INPUT]
- wave_orchestrator.types::ResourceKind / ResourceRecord (POS: ledger schema)

[OUTPUT]
- cleanup_resource_ref() — invoke server API to remove a registered test resource

[POS]
Dev test resource cleanup. Maps ledger kinds to myrm-agent-server REST endpoints.
"""

from __future__ import annotations

import json
import os
import http.cookiejar
import urllib.error
import urllib.request
from typing import TypedDict

from wave_orchestrator.types import ResourceKind

DEFAULT_API_BASE = "http://127.0.0.1:8080"


class CleanupAttempt(TypedDict):
    kind: ResourceKind
    ref: str
    ok: bool
    detail: str


def _api_base() -> str:
    return os.environ.get("MYRM_API_BASE", os.environ.get("E2E_API_BASE", DEFAULT_API_BASE)).rstrip("/")


def _cleanup_timeout() -> float:
    raw = os.environ.get("MYRM_CLEANUP_TIMEOUT_SEC", "5").strip()
    try:
        return max(float(raw), 1.0)
    except ValueError:
        return 5.0


def _admin_password() -> str:
    password = os.environ.get("MYRM_E2E_ADMIN_PASSWORD", os.environ.get("E2E_ADMIN_PASSWORD", "")).strip()
    if not password:
        raise RuntimeError("LEDGER_CLEANUP_AUTH_PASSWORD_MISSING: set MYRM_E2E_ADMIN_PASSWORD or E2E_ADMIN_PASSWORD")
    return password


def _request(
    method: str,
    path: str,
    *,
    cookie: str = "",
    body: dict[str, object] | None = None,
) -> tuple[int, str]:
    url = f"{_api_base()}{path}"
    data = None
    headers = {"Content-Type": "application/json"}
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_cleanup_timeout()) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return exc.code, detail
    except urllib.error.URLError as exc:
        return 0, str(exc)


def _login_cookie() -> str:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    status_url = f"{_api_base()}/webui/auth/status"
    login_url = f"{_api_base()}/webui/auth/login"
    login_body = json.dumps({"username": "admin", "password": _admin_password()}).encode("utf-8")
    try:
        opener.open(status_url, timeout=_cleanup_timeout())
        login_req = urllib.request.Request(
            login_url,
            data=login_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        opener.open(login_req, timeout=_cleanup_timeout())
    except urllib.error.HTTPError as exc:
        if exc.code not in {200, 204}:
            raise RuntimeError(f"LEDGER_CLEANUP_AUTH_LOGIN_FAIL: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LEDGER_CLEANUP_AUTH_LOGIN_FAIL: {exc}") from exc
    parts = [f"{item.name}={item.value}" for item in cookie_jar]
    if not parts:
        raise RuntimeError("LEDGER_CLEANUP_AUTH_LOGIN_FAIL: no session cookie")
    return "; ".join(parts)


def _cleanup_chat(ref: str, cookie: str) -> CleanupAttempt:
    chat_id = ref.strip()
    if not chat_id:
        return {"kind": "chat", "ref": ref, "ok": False, "detail": "empty chat id"}
    status, detail = _request("DELETE", f"/api/v1/chats/{chat_id}", cookie=cookie)
    if status not in {200, 204, 404}:
        return {"kind": "chat", "ref": chat_id, "ok": False, "detail": f"soft-delete HTTP {status}: {detail}"}
    perm_status, perm_detail = _request("DELETE", f"/api/v1/chats/trash/{chat_id}", cookie=cookie)
    if perm_status in {200, 204, 404}:
        return {"kind": "chat", "ref": chat_id, "ok": True, "detail": "permanently deleted"}
    return {
        "kind": "chat",
        "ref": chat_id,
        "ok": False,
        "detail": f"permanent-delete HTTP {perm_status}: {perm_detail}",
    }


def _cleanup_resource(kind: ResourceKind, ref: str, cookie: str) -> CleanupAttempt:
    resource_id = ref.strip()
    if not resource_id:
        return {"kind": kind, "ref": ref, "ok": False, "detail": "empty resource id"}
    paths: dict[ResourceKind, str] = {
        "project": f"/api/v1/projects/{resource_id}",
        "agent": f"/api/v1/agents/{resource_id}",
        "cron": f"/api/v1/cron/{resource_id}",
        "file": f"/api/v1/files/storage/files/{resource_id}",
        "kanban_board": f"/api/v1/kanban/boards/{resource_id}",
        "kanban_task": f"/api/v1/kanban/tasks/{resource_id}",
        "chat": "",
    }
    status, detail = _request("DELETE", paths[kind], cookie=cookie)
    if status in {200, 204, 404}:
        return {"kind": kind, "ref": resource_id, "ok": True, "detail": f"deleted HTTP {status}"}
    return {"kind": kind, "ref": resource_id, "ok": False, "detail": f"delete HTTP {status}: {detail}"}


def cleanup_resource_ref(kind: ResourceKind, ref: str, *, cookie: str = "") -> CleanupAttempt:
    try:
        session_cookie = cookie or _login_cookie()
    except (OSError, RuntimeError, urllib.error.URLError) as exc:
        return {"kind": kind, "ref": ref, "ok": False, "detail": str(exc)}
    if kind == "chat":
        return _cleanup_chat(ref, session_cookie)
    return _cleanup_resource(kind, ref, session_cookie)
