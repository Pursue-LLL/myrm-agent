"""Single physical Chrome pool configuration for parallel Chrome MCP E2E."""

from __future__ import annotations

import os
import platform
from pathlib import Path

from dev_gate_contract import SHARED_BROWSER_WORKERS

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
    home = Path.home()
    if platform.system() == "Darwin":
        return str(home / "Library" / "Application Support/Myrm/ChromeE2E")
    if os.name == "nt":
        return str(home / "AppData/Local/Myrm/ChromeE2E")
    return str(home / ".local/share/myrm/chrome-e2e")


def apply_browser_pool_env() -> dict[str, str]:
    return {
        "MYRM_CHROME_E2E_PORT": str(resolve_chrome_port()),
        "MYRM_CHROME_E2E_DATA_DIR": resolve_chrome_data_dir(),
        "MYRM_E2E_TRANSPORT_CELLS": "1",
        "CDMCP_MUX_MAX_IN_FLIGHT": str(SHARED_BROWSER_WORKERS),
    }


def browser_pool_snapshot() -> dict[str, object]:
    return {
        "logicalSessionsUnlimited": True,
        "physicalWorkers": SHARED_BROWSER_WORKERS,
        "chromePort": resolve_chrome_port(),
        "chromeDataDir": resolve_chrome_data_dir(),
    }
