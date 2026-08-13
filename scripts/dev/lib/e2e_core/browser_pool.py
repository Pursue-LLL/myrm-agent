"""Single physical Chrome pool configuration for parallel Chrome MCP E2E."""

from __future__ import annotations

import os
import platform
from pathlib import Path

from dev_gate.contract import SHARED_BROWSER_WORKERS
from e2e_core.real_user_home import real_user_home

DEFAULT_CHROME_PORT = 9333


def resolve_chrome_port() -> int:
    raw = os.environ.get("MYRM_CHROME_E2E_PORT", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return DEFAULT_CHROME_PORT


def resolve_chrome_data_dir() -> str:
    override = os.environ.get("MYRM_CHROME_E2E_DATA_DIR", "").strip()
    if override:
        return override
    home = real_user_home()
    if platform.system() == "Darwin":
        return str(home / "Library" / "Application Support/Myrm/ChromeE2E")
    if os.name == "nt":
        return str(home / "AppData/Local/Myrm/ChromeE2E")
    return str(home / ".local/share/myrm/chrome-e2e")


def is_canonical_chrome_data_dir(path: str) -> bool:
    """True when data dir is the fixed ChromeE2E profile (P0-C fail-closed)."""
    normalized = Path(path).expanduser()
    text = str(normalized).lower()
    if "/tmp/" in text or "/temp/" in text or "mktemp" in text:
        return False
    return normalized.name in {"ChromeE2E", "chrome-e2e"}


def browser_identity_snapshot() -> dict[str, object]:
    data_dir = resolve_chrome_data_dir()
    port = resolve_chrome_port()
    canonical = is_canonical_chrome_data_dir(data_dir)
    return {
        "chromePort": port,
        "chromeDataDir": data_dir,
        "canonical": canonical,
        "next_action": "READY" if canonical else "BROWSER_IDENTITY_FAIL_CLOSED",
    }


def apply_browser_pool_env() -> dict[str, str]:
    return {
        "MYRM_CHROME_E2E_PORT": str(resolve_chrome_port()),
        "MYRM_CHROME_E2E_DATA_DIR": resolve_chrome_data_dir(),
        "MYRM_E2E_TRANSPORT_CELLS": "1",
        "CDMCP_MUX_MAX_IN_FLIGHT": str(SHARED_BROWSER_WORKERS),
    }


def browser_pool_snapshot() -> dict[str, object]:
    identity = browser_identity_snapshot()
    return {
        "logicalSessionsUnlimited": True,
        "physicalWorkers": SHARED_BROWSER_WORKERS,
        "chromePort": identity["chromePort"],
        "chromeDataDir": identity["chromeDataDir"],
        "canonicalIdentity": identity["canonical"],
        "browserIdentityNextAction": identity["next_action"],
    }
