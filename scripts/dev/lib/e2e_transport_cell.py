"""Chrome Transport Cell pool — lane-routed Chrome/mux stacks (R160-B).

[POS] Dev Gate transport layer. When MYRM_E2E_TRANSPORT_CELLS=2 (chrome_e2e default):
  READ  → cell A (:9333)
  LIVE  → cell B (:9334)
Each cell owns mux cold-attach cap=3; global expensive slots scale with cell count.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dev_gate_contract import MUX_COLD_ATTACH_SLOTS, WAVE_EXPENSIVE_SESSION_SLOTS

DEFAULT_READ_CHROME_PORT = 9333
DEFAULT_LIVE_CHROME_PORT = 9334
ENV_TRANSPORT_CELLS = "MYRM_E2E_TRANSPORT_CELLS"


def active_transport_cell_count() -> int:
    raw = os.environ.get(ENV_TRANSPORT_CELLS, "").strip()
    if not raw.isdigit():
        return 1
    return max(1, min(2, int(raw)))


def resolve_chrome_port_for_lane(lane: str) -> int:
    normalized = lane.strip().upper()
    if active_transport_cell_count() < 2:
        read_raw = os.environ.get("MYRM_E2E_READ_CHROME_PORT", "").strip()
        if read_raw.isdigit():
            return int(read_raw)
        return DEFAULT_READ_CHROME_PORT
    if normalized == "LIVE_AGENT":
        live_raw = os.environ.get("MYRM_E2E_LIVE_CHROME_PORT", "").strip()
        if live_raw.isdigit():
            return int(live_raw)
        return DEFAULT_LIVE_CHROME_PORT
    read_raw = os.environ.get("MYRM_E2E_READ_CHROME_PORT", "").strip()
    if read_raw.isdigit():
        return int(read_raw)
    return DEFAULT_READ_CHROME_PORT


def resolve_chrome_data_dir_for_port(port: int) -> str:
    override = os.environ.get("MYRM_CHROME_E2E_DATA_DIR", "").strip()
    if override and port == resolve_chrome_port_for_lane("READ"):
        return override
    if port == DEFAULT_LIVE_CHROME_PORT:
        live_override = os.environ.get("MYRM_E2E_LIVE_CHROME_DATA_DIR", "").strip()
        if live_override:
            return live_override
        home = Path.home()
        if sys.platform == "darwin":
            return str(
                home / "Library" / "Application Support" / "Myrm" / "ChromeE2ELive"
            )
        if sys.platform.startswith("linux"):
            return str(home / ".local" / "share" / "myrm" / "chrome-e2e-live")
        return str(home / ".myrm" / "chrome-e2e-live")
    home = Path.home()
    if sys.platform == "darwin":
        return str(home / "Library" / "Application Support" / "Myrm" / "ChromeE2E")
    if sys.platform.startswith("linux"):
        return str(home / ".local" / "share" / "myrm" / "chrome-e2e")
    return str(home / ".myrm" / "chrome-e2e")


def apply_lane_transport_env(lane: str) -> dict[str, str]:
    """Return env updates for the current chrome_e2e session lane."""
    port = resolve_chrome_port_for_lane(lane)
    data_dir = resolve_chrome_data_dir_for_port(port)
    updates = {
        "MYRM_CHROME_E2E_PORT": str(port),
        "MYRM_CHROME_E2E_DATA_DIR": data_dir,
        ENV_TRANSPORT_CELLS: str(active_transport_cell_count()),
    }
    normalized = lane.strip().upper()
    if normalized == "LIVE_AGENT":
        updates["MYRM_E2E_LIVE_CHROME_PORT"] = str(port)
    else:
        updates["MYRM_E2E_READ_CHROME_PORT"] = str(port)
    return updates


def list_required_chrome_ports() -> list[int]:
    count = active_transport_cell_count()
    if count < 2:
        return [resolve_chrome_port_for_lane("READ")]
    return sorted(
        {
            resolve_chrome_port_for_lane("READ"),
            resolve_chrome_port_for_lane("LIVE_AGENT"),
        }
    )


def effective_expensive_session_slots() -> int:
    """Global wave expensive slots = per-cell cap × active cells."""
    per_cell = WAVE_EXPENSIVE_SESSION_SLOTS
    override = os.environ.get("MYRM_WAVE_EXPENSIVE_SESSION_SLOTS", "").strip()
    if override.isdigit() and int(override) > 0:
        per_cell = int(override)
    return per_cell * active_transport_cell_count()


def per_cell_mux_cold_attach_cap() -> int:
    return MUX_COLD_ATTACH_SLOTS


def transport_cell_snapshot() -> dict[str, object]:
    count = active_transport_cell_count()
    read_port = resolve_chrome_port_for_lane("READ")
    live_port = resolve_chrome_port_for_lane("LIVE_AGENT") if count >= 2 else None
    return {
        "activeCells": count,
        "readChromePort": read_port,
        "liveChromePort": live_port,
        "perCellMuxCap": MUX_COLD_ATTACH_SLOTS,
        "globalExpensiveSlots": effective_expensive_session_slots(),
        "requiredChromePorts": list_required_chrome_ports(),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chrome transport cell routing (R160-B)")
    sub = parser.add_subparsers(dest="command", required=True)
    apply_cmd = sub.add_parser("apply-lane")
    apply_cmd.add_argument("--lane", required=True)
    sub.add_parser("snapshot")
    ensure = sub.add_parser("ensure-ports")
    ensure.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "apply-lane":
        payload = apply_lane_transport_env(args.lane)
        for key, value in payload.items():
            print(f"{key}={value}")
        return 0
    if args.command == "snapshot":
        print(json.dumps(transport_cell_snapshot(), indent=2, sort_keys=True))
        return 0
    if args.command == "ensure-ports":
        ports = list_required_chrome_ports()
        if args.json:
            print(json.dumps({"ports": ports}, indent=2, sort_keys=True))
        else:
            for port in ports:
                print(port)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
