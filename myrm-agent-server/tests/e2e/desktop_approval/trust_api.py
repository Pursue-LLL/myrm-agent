"""Server API helpers for desktop approval Chrome E2E.

[INPUT]
- cdp_chat.support::get_e2e_api_url (POS: live E2E API base resolver)
- tests.e2e.desktop_approval.constants::progress (POS: stderr progress lines)

[OUTPUT]
- HTTP trust/approval helpers; desktop_trust_revoke_selector_js for Settings revoke E2E

[POS]
Server-side REST helpers and safe DOM selector builders for desktop approval Chrome E2E.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from cdp_chat.support import (
    _e2e_api_get_json,
    _e2e_api_urlopen,
    fetch_chat_messages,
    get_e2e_api_url,
)

from tests.e2e.desktop_approval.constants import progress

_DESKTOP_DREF_PATTERN = re.compile(r"@(d\d+)\b")


def _append_dref_scan_chunks(chunks: list[str], value: object) -> None:
    if isinstance(value, str):
        chunks.append(value)
        return
    if isinstance(value, dict):
        refs = value.get("refs")
        if isinstance(refs, dict):
            for ref_key in refs:
                if isinstance(ref_key, str) and ref_key.startswith("d"):
                    chunks.append(f"@{ref_key}")
        chunks.append(json.dumps(value, ensure_ascii=False))
        return
    if isinstance(value, list):
        for item in value:
            _append_dref_scan_chunks(chunks, item)
        return
    if value is not None:
        chunks.append(json.dumps(value, ensure_ascii=False))


def extract_first_desktop_dref_from_messages(
    messages: list[object],
) -> str | None:
    """Parse first @dref from persisted assistant progress (API SSOT under TextEdit foreground)."""
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        chunks: list[str] = []
        content = msg.get("content")
        if isinstance(content, str):
            chunks.append(content)
        metadata = msg.get("metadata")
        meta = metadata if isinstance(metadata, dict) else {}
        top_steps_raw = msg.get("progressSteps")
        if isinstance(top_steps_raw, list):
            steps = top_steps_raw
        else:
            steps_raw = meta.get("progressSteps")
            steps = steps_raw if isinstance(steps_raw, list) else []
        for step in steps:
            if not isinstance(step, dict):
                continue
            for key in ("stdout", "items", "output", "result"):
                _append_dref_scan_chunks(chunks, step.get(key))
        match = _DESKTOP_DREF_PATTERN.search("\n".join(chunks))
        if match:
            return match.group(1)
    return None


def _dref_from_snapshot_payload(payload: dict[str, object]) -> str | None:
    refs = payload.get("refs")
    if not isinstance(refs, dict) or not refs:
        return None
    for ref_key in sorted(refs):
        normalized = str(ref_key).strip().lstrip("@")
        if normalized.startswith("d") and len(normalized) > 1:
            return normalized
    return None


def fetch_first_desktop_dref_from_local_capture() -> str | None:
    """Local AX capture fallback when gateway desktop snapshot sources are unavailable."""
    import platform

    if platform.system() != "Darwin":
        return None
    from myrm_agent_harness.toolkits.computer_use.backends.macos import MacOSBackend
    from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef
    from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import (
        capture_snapshot,
    )

    backend = MacOSBackend()
    preferred_roles = {"text", "statictext", "axtextarea", "scrollarea"}
    strategies: tuple[tuple[str, str | None], ...] = (
        ("target", "TextEdit"),
        ("foreground", None),
    )

    for scope, app_name in strategies:
        try:
            meta, refs = capture_snapshot(backend, scope, app_name)
        except OSError as exc:
            progress(
                "local AX capture failed "
                f"scope={scope} app={app_name!r}: {exc}"
            )
            continue
        except Exception as exc:
            progress(
                "local AX capture failed "
                f"scope={scope} app={app_name!r}: {type(exc).__name__}: {exc}"
            )
            continue

        element_refs = {
            key: value for key, value in refs.items() if isinstance(value, ElementRef)
        }
        if not element_refs:
            progress(
                "local AX capture refs empty "
                f"scope={scope} app={meta.app_name!r} window={meta.window_title!r}"
            )
            continue

        for ref_key, ref in element_refs.items():
            role = str(getattr(ref, "role", "") or "").lower()
            normalized = str(ref_key).strip().lstrip("@")
            if (
                role in preferred_roles
                and normalized.startswith("d")
                and len(normalized) > 1
            ):
                progress(
                    "dref from local AX capture "
                    f"scope={scope} role={role!r}: {normalized!r} app={meta.app_name!r}"
                )
                return normalized
        for ref_key in sorted(element_refs):
            normalized = str(ref_key).strip().lstrip("@")
            if normalized.startswith("d") and len(normalized) > 1:
                progress(
                    "dref from local AX capture fallback "
                    f"scope={scope}: {normalized!r}"
                )
                return normalized
    return None


def fetch_first_desktop_dref_from_snapshot_api(*, chat_id: str = "") -> str | None:
    """Read first @dref from desktop snapshot API (registry → live → foreground_e2e)."""
    base = get_e2e_api_url()
    chat_q = (
        f"&chat_id={urllib.parse.quote(chat_id.strip())}" if chat_id.strip() else ""
    )
    sources = ("registry", "live", "foreground_e2e")
    for source in sources:
        query = f"source={source}"
        if source != "foreground_e2e":
            query = f"{query}{chat_q}"
        url = f"{base}/webui/desktop/snapshot?{query}"
        try:
            payload = _e2e_api_get_json(url, timeout_sec=8.0, max_attempts=2)
        except OSError as exc:
            detail = str(exc)
            if isinstance(exc, urllib.error.HTTPError):
                try:
                    body = exc.read().decode("utf-8")
                    parsed = json.loads(body)
                    if isinstance(parsed, dict):
                        detail = (
                            f"{parsed.get('error', exc.code)}: "
                            f"{parsed.get('message', body)}"
                        )
                except OSError:
                    detail = f"HTTP {exc.code}"
            progress(f"snapshot API fetch failed source={source}: {detail}")
            continue
        if not isinstance(payload, dict):
            progress(
                f"snapshot API unexpected payload type source={source}: "
                f"{type(payload).__name__}"
            )
            continue
        error = payload.get("error")
        if error:
            progress(
                f"snapshot API error source={source}: {error} — "
                f"{payload.get('message', '')}"
            )
            continue
        dref = _dref_from_snapshot_payload(payload)
        if dref:
            progress(f"dref from snapshot API source={source}: {dref!r}")
            return dref
        progress(
            f"snapshot API refs empty source={source}: "
            f"app_name={payload.get('app_name')!r} "
            f"needs_permission={payload.get('needs_permission')}"
        )
    local_dref = fetch_first_desktop_dref_from_local_capture()
    if local_dref:
        return local_dref
    return None


def fetch_first_desktop_dref_from_api(
    chat_id: str,
    *,
    timeout_sec: float = 15.0,
    max_attempts: int = 3,
) -> str | None:
    normalized = chat_id.strip()
    if not normalized:
        return None
    messages = fetch_chat_messages(
        normalized,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    if not messages:
        return None
    return extract_first_desktop_dref_from_messages(messages)


def fetch_desktop_tool_progress_from_api(
    chat_id: str,
    *,
    timeout_sec: float = 15.0,
    max_attempts: int = 3,
) -> dict[str, object] | None:
    """Read desktop tool progress from persisted chat messages (SSE/UI may lag)."""
    normalized = chat_id.strip()
    if not normalized:
        return None
    messages = fetch_chat_messages(
        normalized,
        timeout_sec=timeout_sec,
        max_attempts=max_attempts,
    )
    if not messages:
        return None
    user_count = sum(
        1 for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"
    )
    last_assistant: dict[str, object] | None = None
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            last_assistant = msg
    if last_assistant is None:
        return {
            "active": False,
            "isStreaming": user_count > 0,
            "pending": False,
            "stepCount": 0,
            "lastTool": "",
            "assistantSample": "",
            "completionStatus": "",
            "source": "api",
        }
    metadata = last_assistant.get("metadata")
    meta = metadata if isinstance(metadata, dict) else {}
    steps_raw = meta.get("progressSteps")
    steps = steps_raw if isinstance(steps_raw, list) else []
    desktop_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("tool_name") or "").startswith("desktop_")
    ]
    completion_status = str(meta.get("completionStatus") or "")
    assistant_sample = str(last_assistant.get("content") or "")[:200]
    is_complete = completion_status in {"complete", "error", "cancelled"}
    return {
        "active": len(desktop_steps) > 0,
        "isStreaming": user_count > 0 and not is_complete,
        "pending": False,
        "stepCount": len(desktop_steps),
        "lastTool": (
            str(desktop_steps[-1].get("tool_name") or "") if desktop_steps else ""
        ),
        "assistantSample": assistant_sample,
        "completionStatus": completion_status,
        "source": "api",
    }


def server_pending_approval_count(
    *,
    timeout_sec: float = 8.0,
    max_attempts: int = 3,
) -> int:
    url = f"{get_e2e_api_url()}/webui/desktop/approval/pending"
    try:
        payload = _e2e_api_get_json(
            url, timeout_sec=timeout_sec, max_attempts=max_attempts
        )
    except OSError:
        return -1
    if not isinstance(payload, dict):
        return -1
    return int(payload.get("count") or 0)


def fetch_pending_approval_request_ids() -> list[str]:
    url = f"{get_e2e_api_url()}/webui/desktop/approval/pending"
    try:
        payload = _e2e_api_get_json(url, timeout_sec=8.0, max_attempts=3)
    except OSError:
        return []
    if not isinstance(payload, dict):
        return []
    pending = payload.get("pending")
    if not isinstance(pending, list):
        return []
    return [str(item).strip() for item in pending if str(item).strip()]


def seed_pending_desktop_approval_for_test(
    *,
    app_name: str = "TextEdit",
    operation: str = "foreground_control",
    reason: str = "Allow Myrm to control TextEdit for this task?",
    require_app_approval: bool = True,
) -> str | None:
    """Create a local/test pending desktop approval request for E2E fallback."""
    url = f"{get_e2e_api_url()}/webui/desktop/approval/test-seed"
    payload = {
        "app_name": app_name,
        "operation": operation,
        "reason": reason,
        "window_title": "",
        "app_id": "",
        "require_app_approval": require_app_approval,
    }
    try:
        request = urllib.request.Request(  # noqa: S310
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
        )
        request.add_header("Content-Type", "application/json")
        with _e2e_api_urlopen(
            request,
            timeout_sec=10.0,
            max_attempts=2,
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        progress(f"desktop approval test-seed failed: {exc}")
        return None
    if not isinstance(body, dict) or body.get("ok") is not True:
        progress(f"desktop approval test-seed unexpected response: {body!r}")
        return None
    request_id = str(body.get("request_id") or "").strip()
    if not request_id:
        progress(f"desktop approval test-seed missing request_id: {body!r}")
        return None
    progress(f"desktop approval test-seed request_id={request_id}")
    return request_id


def resolve_pending_desktop_approval_for_test(*, scope: str = "once") -> bool:
    """Resolve first pending desktop approval via server API (E2E fallback)."""
    pending_ids = fetch_pending_approval_request_ids()
    if not pending_ids:
        return False
    return resolve_desktop_approval_request_for_test(pending_ids[0], scope=scope)


def resolve_desktop_approval_request_for_test(
    request_id: str,
    *,
    scope: str = "once",
) -> bool:
    """Resolve a specific desktop approval request id via server API fallback."""
    normalized_request_id = request_id.strip()
    if not normalized_request_id:
        return False
    payload = {
        "request_id": normalized_request_id,
        "granted": True,
        "scope": scope,
    }
    url = f"{get_e2e_api_url()}/webui/desktop/approval/resolve"
    try:
        request = urllib.request.Request(  # noqa: S310
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
        )
        request.add_header("Content-Type", "application/json")
        with _e2e_api_urlopen(
            request,
            timeout_sec=10.0,
            max_attempts=2,
        ) as response:
            body = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        progress(
            "desktop approval resolve fallback failed "
            f"request_id={normalized_request_id}: {exc}"
        )
        return False
    if not isinstance(body, dict) or body.get("ok") is not True:
        progress(
            "desktop approval resolve fallback unexpected response "
            f"request_id={normalized_request_id}: {body!r}"
        )
        return False
    progress(
        "desktop approval resolve fallback ok "
        f"request_id={normalized_request_id} scope={scope}"
    )
    return True


def list_trusted_apps_via_api() -> list[dict[str, object]]:
    url = f"{get_e2e_api_url()}/webui/desktop/trust/apps"
    try:
        request = urllib.request.Request(  # noqa: S310 - validated in _e2e_api_urlopen
            url, method="GET"
        )
        with _e2e_api_urlopen(
            request,
            timeout_sec=5.0,
            max_attempts=3,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        raise AssertionError(f"Failed to list trusted apps: {exc}") from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"Unexpected trust list payload: {payload!r}")
    apps = payload.get("apps")
    if not isinstance(apps, list):
        raise AssertionError(f"Unexpected trust list apps: {payload!r}")
    return apps


def clear_persisted_desktop_approvals() -> None:
    data_dir = os.environ.get("MYRM_DATA_DIR", "").strip()
    if data_dir:
        approval_path = (
            Path(data_dir) / ".agent" / "desktop_control" / "approved_apps.json"
        )
        if approval_path.is_file():
            approval_path.unlink(missing_ok=True)
    reset_url = f"{get_e2e_api_url()}/webui/desktop/approval/reset-runtime"
    try:
        request = urllib.request.Request(  # noqa: S310
            reset_url, method="POST", data=b"{}"
        )
        request.add_header("Content-Type", "application/json")
        with _e2e_api_urlopen(
            request,
            timeout_sec=10.0,
            max_attempts=3,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError as exc:
        progress(f"desktop approval reset skipped: {exc}")
        return
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        progress(f"desktop approval reset unexpected response: {payload}")
        return
    try:
        apps = list_trusted_apps_via_api()
        for app in apps:
            trust_key = str(app.get("trust_key") or "").strip()
            if not trust_key:
                continue
            revoke_request = urllib.request.Request(  # noqa: S310
                f"{get_e2e_api_url()}/webui/desktop/trust/apps",
                method="DELETE",
                data=json.dumps({"trust_key": trust_key}).encode("utf-8"),
            )
            revoke_request.add_header("Content-Type", "application/json")
            with _e2e_api_urlopen(
                revoke_request,
                timeout_sec=10.0,
                max_attempts=3,
            ):
                pass
    except OSError as exc:
        progress(f"trusted apps clear skipped: {exc}")


def desktop_accessibility_granted() -> bool:
    url = f"{get_e2e_api_url()}/webui/desktop/permissions"
    try:
        request = urllib.request.Request(  # noqa: S310 - validated in _e2e_api_urlopen
            url, method="GET"
        )
        with _e2e_api_urlopen(
            request,
            timeout_sec=10.0,
            max_attempts=3,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except OSError:
        return False
    return bool(payload.get("accessibility"))


def desktop_trust_revoke_testid(trust_key: str) -> str:
    return f"desktop-trust-revoke-{trust_key}"


def desktop_trust_revoke_selector_js(trust_key: str) -> str:
    """Return a JS expression safe for querySelector on the revoke button testid."""
    return json.dumps(f'[data-testid="{desktop_trust_revoke_testid(trust_key)}"]')
