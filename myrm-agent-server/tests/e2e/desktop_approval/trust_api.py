"""Server API helpers for desktop approval Chrome E2E.

[INPUT]
- cdp_chat_support::get_e2e_api_url (POS: live E2E API base resolver)
- tests.e2e.desktop_approval.constants::progress (POS: stderr progress lines)

[OUTPUT]
- HTTP trust/approval helpers; desktop_trust_revoke_selector_js for Settings revoke E2E

[POS]
Server-side REST helpers and safe DOM selector builders for desktop approval Chrome E2E.
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from cdp_chat_support import _e2e_api_get_json, get_e2e_api_url

from tests.e2e.desktop_approval.constants import progress


def server_pending_approval_count() -> int:
    url = f"{get_e2e_api_url()}/webui/desktop/approval/pending"
    try:
        payload = _e2e_api_get_json(url, timeout_sec=8.0, max_attempts=3)
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


def list_trusted_apps_via_api() -> list[dict[str, object]]:
    url = f"{get_e2e_api_url()}/webui/desktop/trust/apps"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310
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
        approval_path = Path(data_dir) / ".agent" / "desktop_control" / "approved_apps.json"
        if approval_path.is_file():
            approval_path.unlink(missing_ok=True)
    reset_url = f"{get_e2e_api_url()}/webui/desktop/approval/reset-runtime"
    try:
        request = urllib.request.Request(reset_url, method="POST", data=b"{}")  # noqa: S310
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
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
            with urllib.request.urlopen(revoke_request, timeout=10):  # noqa: S310
                pass
    except OSError as exc:
        progress(f"trusted apps clear skipped: {exc}")


def desktop_accessibility_granted() -> bool:
    url = f"{get_e2e_api_url()}/webui/desktop/permissions"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except OSError:
        return False
    return bool(payload.get("accessibility"))


def desktop_trust_revoke_testid(trust_key: str) -> str:
    return f"desktop-trust-revoke-{trust_key}"


def desktop_trust_revoke_selector_js(trust_key: str) -> str:
    """Return a JS expression safe for querySelector on the revoke button testid."""
    return json.dumps(f'[data-testid="{desktop_trust_revoke_testid(trust_key)}"]')
