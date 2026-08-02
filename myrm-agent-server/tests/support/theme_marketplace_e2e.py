"""Theme marketplace Chrome MCP E2E helpers.

[INPUT]
- control_plane.auth.tokens::generate_api_token (POS: CP JWT/API token 工具层)
- scripts/seed_official_theme_listings.py (POS: 官方主题 seed CLI)

[OUTPUT]
- cp_reachable(), seed_official_listing(), issue_cp_auth_token(), fetch_official_free_listing_id()

[POS]
Theme marketplace Chrome E2E 准备层。CP 探活、seed 与 listing 查询 SSOT。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CP_ROOT = _REPO_ROOT / "myrm-control-plane"
_SEED_SCRIPT = _CP_ROOT / "scripts" / "seed_official_theme_listings.py"


def cp_base_url() -> str:
    configured = os.environ.get("MYRM_CP_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    host = os.environ.get("MYRM_E2E_CP_HOST", "127.0.0.1").strip()
    port = os.environ.get("MYRM_CP_PORT", "8003").strip()
    return f"http://{host}:{port}"


def cp_reachable() -> bool:
    url = f"{cp_base_url()}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def cp_jwt_secret() -> str | None:
    secret = os.environ.get("MYRM_CP_JWT_SECRET", "").strip()
    if secret:
        return secret
    secret = os.environ.get("JWT_SECRET", "").strip()
    return secret or None


def issue_cp_auth_token(user_id: str) -> str | None:
    secret = cp_jwt_secret()
    if not secret:
        return None
    cp_src = _CP_ROOT / "src"
    if str(cp_src) not in sys.path:
        sys.path.insert(0, str(cp_src))
    from myrm_control_plane.auth.tokens import generate_api_token

    return generate_api_token(user_id=user_id, jwt_secret=secret)


def seed_official_listing() -> None:
    if not _SEED_SCRIPT.is_file():
        raise FileNotFoundError(f"Seed script not found: {_SEED_SCRIPT}")
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, str(_SEED_SCRIPT)],
        cwd=str(_CP_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Official theme seed failed: {detail or result.returncode}")


def fetch_official_free_listing_id(*, auth_token: str | None = None) -> str | None:
    url = f"{cp_base_url()}/api/theme-marketplace/list?origin=official"
    request = urllib.request.Request(url)
    if auth_token:
        request.add_header("Authorization", f"Bearer {auth_token}")
    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    for row in payload:
        if not isinstance(row, dict):
            continue
        price = int(row.get("price_cents") or row.get("priceCents") or 0)
        status = str(row.get("status") or "")
        listing_id = str(row.get("id") or "")
        if price == 0 and status == "published" and listing_id:
            return listing_id
    return None


def acquire_theme_listing_for_e2e(*, listing_id: str, auth_token: str) -> None:
    url = f"{cp_base_url()}/api/theme-marketplace/listing/{listing_id}/acquire"
    request = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {auth_token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20.0) as response:
            if response.status >= 400:
                raise RuntimeError(f"Theme acquire failed: HTTP {response.status}")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Theme acquire failed: HTTP {error.code} {body}") from error
