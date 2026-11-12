"""Chrome CDP and CDMCP mux epoch readers for Chrome MCP E2E.

[INPUT]
- CDP GET /json/version on the E2E Chrome port, default :9333 (POS: Myrm E2E Chrome attach endpoint)
- ~/.local/state/cdmcp-mux daemon.pid + upstream-ws-url (POS: mux daemon generation stamp)
- MYRM_CHROME_E2E_PORT / MYRM_CHROME_E2E_DATA_DIR / CHROME_DATA_DIR / CDMCP_MUX_STATE_DIR overrides (POS: per-lane isolation of port, profile and mux state)

[OUTPUT]
- `read_chrome_epoch()`: `ChromeEpoch` (cdp_port, browser_id, web_socket_url, profile_dir) or `None`
- `read_mux_epoch()`: `MuxEpoch` (daemon_pid, ws_url, upstream_ready, upstream_generation) or `None`
- `resolve_e2e_port()` / `default_chrome_data_dir()` / `mux_state_dir()`: E2E port, Chrome profile dir and mux state dir resolved from the environment

[POS]
Dev infrastructure. Observes the browser plane; never mutates it.
"""

from __future__ import annotations

import json
import os
import platform
import re
import urllib.error
import urllib.request
from pathlib import Path

from e2e_core.real_user_home import real_user_home
from e2e_core.runtime_types import ChromeEpoch, MuxEpoch

_BROWSER_ID_RE = re.compile(r"/devtools/browser/([0-9a-f-]{36})")


def mux_state_dir() -> Path:
    override = os.getenv("CDMCP_MUX_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return real_user_home() / ".local/state/cdmcp-mux"


def default_chrome_data_dir() -> Path:
    from_env = (
        os.getenv("MYRM_CHROME_E2E_DATA_DIR", "").strip()
        or os.getenv("CHROME_DATA_DIR", "").strip()
    )
    if from_env:
        return Path(from_env)
    if os.name == "nt":
        return real_user_home() / "AppData/Local/Myrm/ChromeE2E"
    if platform.system() == "Darwin":
        return real_user_home() / "Library/Application Support/Myrm/ChromeE2E"
    return real_user_home() / ".local/share/myrm/chrome-e2e"


def resolve_e2e_port() -> int:
    raw = os.getenv("MYRM_CHROME_E2E_PORT", "9333").strip()
    if raw.isdigit():
        return int(raw)
    return 9333


def _fetch_cdp_version(port: int) -> dict[str, object]:
    url = f"http://127.0.0.1:{port}/json/version"
    with urllib.request.urlopen(url, timeout=5) as resp:
        payload = json.load(resp)
    if not isinstance(payload, dict):
        raise TypeError(f"Invalid /json/version payload on port {port}")
    return payload


def _browser_id_from_ws_url(ws_url: str) -> str:
    match = _BROWSER_ID_RE.search(ws_url)
    if match:
        return match.group(1)
    return ws_url


def read_chrome_epoch(
    port: int | None = None,
    profile_dir: Path | None = None,
) -> ChromeEpoch | None:
    cdp_port = port if port is not None else resolve_e2e_port()
    profile = profile_dir if profile_dir is not None else default_chrome_data_dir()
    try:
        payload = _fetch_cdp_version(cdp_port)
    except (OSError, TypeError, urllib.error.URLError, ValueError, json.JSONDecodeError):
        return None
    ws_url = payload.get("webSocketDebuggerUrl")
    if not isinstance(ws_url, str) or not ws_url.startswith("ws://"):
        return None
    return {
        "cdp_port": cdp_port,
        "browser_id": _browser_id_from_ws_url(ws_url),
        "web_socket_url": ws_url,
        "profile_dir": str(profile),
    }


def read_mux_epoch(
    *,
    upstream_ready: bool,
    ws_stamp_matches: bool,
    mux_daemon_count: int,
    upstream_generation: int = 0,
) -> MuxEpoch | None:
    if mux_daemon_count < 1:
        return None
    pid_path = mux_state_dir() / "daemon.pid"
    daemon_pid: int | None = None
    if pid_path.is_file():
        try:
            parsed = int(pid_path.read_text(encoding="utf-8").strip())
            if parsed > 0:
                daemon_pid = parsed
        except (OSError, ValueError):
            daemon_pid = None
    ws_stamp_path = mux_state_dir() / "upstream-ws-url"
    ws_url = ""
    if ws_stamp_path.is_file():
        ws_url = ws_stamp_path.read_text(encoding="utf-8").strip()
    if not ws_url and ws_stamp_matches:
        chrome = read_chrome_epoch()
        if chrome is not None:
            ws_url = chrome["web_socket_url"]
    return {
        "daemon_pid": daemon_pid,
        "ws_url": ws_url,
        "upstream_ready": upstream_ready,
        "upstream_generation": max(upstream_generation, 0),
    }
