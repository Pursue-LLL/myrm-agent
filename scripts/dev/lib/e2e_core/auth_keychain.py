"""macOS Keychain-backed auth cookie blob storage for Chrome E2E (P0-C)."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path
from e2e_core.real_user_home import real_user_home

_KEYCHAIN_ACCOUNT = "myrm-e2e-auth"
_SERVICE_PREFIX = "myrm-e2e-auth-cookies"


def keychain_storage_enabled() -> bool:
    if sys.platform != "darwin":
        return False
    return os.environ.get("MYRM_E2E_AUTH_KEYCHAIN", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _fallback_secrets_path(template_fingerprint: str) -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    base = Path(override) if override else real_user_home() / ".local/state/myrm-dev"
    safe_fp = template_fingerprint.strip().replace("/", "_") or "unknown"
    return base / f"e2e-auth-cookies-{safe_fp}.blob"


def _service_name(template_fingerprint: str) -> str:
    return f"{_SERVICE_PREFIX}-{template_fingerprint.strip()}"


def store_auth_cookie_blob(
    template_fingerprint: str,
    cookies: list[dict[str, object]],
) -> str:
    """Persist cookie payload outside plain template JSON; returns blob ref."""
    normalized_fp = template_fingerprint.strip()
    if not normalized_fp:
        raise ValueError("template_fingerprint is required")
    payload = json.dumps(cookies, separators=(",", ":"), sort_keys=True).encode("utf-8")
    encoded = base64.b64encode(payload).decode("ascii")
    if keychain_storage_enabled():
        service = _service_name(normalized_fp)
        subprocess.run(
            [
                "security",
                "add-generic-password",
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-s",
                service,
                "-w",
                encoded,
                "-U",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return f"keychain:{service}"
    path = _fallback_secrets_path(normalized_fp)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return f"file:{path}"


def load_auth_cookie_blob(blob_ref: str) -> list[dict[str, object]] | None:
    ref = blob_ref.strip()
    if not ref:
        return None
    encoded = ""
    if ref.startswith("keychain:"):
        service = ref.split(":", 1)[1].strip()
        if not service:
            return None
        try:
            completed = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a",
                    _KEYCHAIN_ACCOUNT,
                    "-s",
                    service,
                    "-w",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError:
            return None
        encoded = completed.stdout.strip()
    elif ref.startswith("file:"):
        path = Path(ref.split(":", 1)[1].strip())
        try:
            encoded = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
    else:
        return None
    if not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, list):
        return None
    cookies: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, dict):
            cookies.append(item)
    return cookies


def delete_auth_cookie_blob(blob_ref: str) -> None:
    ref = blob_ref.strip()
    if ref.startswith("keychain:"):
        service = ref.split(":", 1)[1].strip()
        if not service:
            return
        subprocess.run(
            [
                "security",
                "delete-generic-password",
                "-a",
                _KEYCHAIN_ACCOUNT,
                "-s",
                service,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        return
    if ref.startswith("file:"):
        path = Path(ref.split(":", 1)[1].strip())
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
