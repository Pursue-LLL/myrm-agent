"""CDP write gate — raw target creation is forbidden outside the MCP mux.

[INPUT]
- wave_orchestrator store state (POS: diagnostics for active lease records)

[OUTPUT]
- cdp_write_allowed() / assert_cdp_write_allowed() — fail-fast before direct /json/new

[POS]
Dev infrastructure. Prevents pytest/bun raw CDP from racing mux during parallel MCP E2E.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


class CdpWriteDecision(TypedDict):
    allowed: bool
    reason: str
    active_leases: int


def _state_file() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    root = Path(override) if override else Path.home() / ".local/state/myrm-dev"
    return root / "wave-orchestrator.json"


def _count_active_leases() -> int:
    path = _state_file()
    if not path.is_file():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    leases = payload.get("leases")
    if not isinstance(leases, list):
        return 0
    now = datetime.now(timezone.utc)
    count = 0
    for item in leases:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "active":
            continue
        expires = item.get("expiresAt")
        if isinstance(expires, str):
            try:
                exp_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if exp_dt <= now:
                    continue
            except ValueError:
                pass
        count += 1
    return count


def cdp_write_allowed(*, operation: str = "json/new") -> CdpWriteDecision:
    active = _count_active_leases()
    if os.getenv("MYRM_CDP_WARMUP", "").strip() == "1":
        return {
            "allowed": True,
            "reason": "supervisor-warmup",
            "active_leases": active,
        }
    return {
        "allowed": False,
        "reason": (
            f"CDP_WRITE_DENIED: raw {operation} is disabled; use the chrome-devtools "
            f"MCP mux owner path (active leases={active})"
        ),
        "active_leases": active,
    }


def assert_cdp_write_allowed(*, operation: str = "json/new") -> None:
    decision = cdp_write_allowed(operation=operation)
    if not decision["allowed"]:
        raise RuntimeError(decision["reason"])


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Check whether direct CDP writes are allowed.")
    parser.add_argument("--operation", default="json/new")
    parser.add_argument("--json", action="store_true", help="Emit JSON decision")
    args = parser.parse_args()
    decision = cdp_write_allowed(operation=args.operation)
    if args.json:
        print(json.dumps(decision, separators=(",", ":")))
    else:
        print(decision["reason"])
    return 0 if decision["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
