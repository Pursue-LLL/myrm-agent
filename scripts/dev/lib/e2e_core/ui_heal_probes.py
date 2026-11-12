"""Reachability probes of the shared UI for the heal: root HTML, one route and the hydrated client.

[INPUT]
- `MYRM_E2E_UI_BASE` or `e2e_core.dev_ports::shared_ui_base` (POS: Default ports of the user, shared dev and isolated stacks — SSOT)
- `e2e_core.endpoint_health::frontend_tcp_html_probe_ok`, `e2e_core.frontend_epoch` hot state (POS: live and recorded state of the frontend)

[OUTPUT]
- `shared_ui_probe_ok()` / `route_probe_ok()` / `shared_client_hot_ok()`: boolean probes that answer False for an unreachable UI instead of raising

[POS]
Dev infrastructure. Read-only observation of the shared UI; the decision to heal lives in `warm_ui_heal.py`.
"""

from __future__ import annotations

import os

from e2e_core.dev_ports import shared_ui_base


def shared_ui_probe_ok(*, timeout_sec: float = 12.0) -> bool:
    ui_base = os.environ.get("MYRM_E2E_UI_BASE", shared_ui_base()).rstrip("/")
    try:
        from e2e_core.endpoint_health import frontend_tcp_html_probe_ok

        return frontend_tcp_html_probe_ok(ui_base, timeout_sec=timeout_sec)
    except (ImportError, OSError, ValueError):
        return False


def shared_client_hot_ok() -> bool:
    """HTTP 200 alone is insufficient — Turbopack can stall with app-shell-skeleton."""
    try:
        from e2e_core.frontend_epoch import (
            read_frontend_epoch,
            read_frontend_hot_state,
        )

        frontend = read_frontend_epoch()
        _, client_hot = read_frontend_hot_state(frontend)
        return client_hot
    except (ImportError, OSError, TypeError, ValueError):
        return False


def route_probe_ok(route: str, *, timeout_sec: float = 12.0) -> bool:
    import urllib.error
    import urllib.request

    ui_base = os.environ.get("MYRM_E2E_UI_BASE", shared_ui_base()).rstrip("/")
    path = route if route.startswith("/") else f"/{route}"
    request = urllib.request.Request(f"{ui_base}{path}", method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False
