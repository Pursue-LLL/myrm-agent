"""Tab hygiene report for ./myrm doctor --chrome.

[INPUT]
- CDP /json/list page count
- wave-orchestrator.json lease bindings
- infra_browser_registry.list_infra_targets()

[OUTPUT]
- build_tab_hygiene_report() and CLI --report line for doctor

[POS]
Dev Chrome E2E observability. Counts only; never closes tabs by URL inference.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import TypedDict


class TabHygieneReport(TypedDict):
    cdpOpenTargets: int
    waveBoundLeases: int
    infraRegistryTargets: int
    ok: bool
    detail: str


def _chrome_port() -> int:
    raw = os.environ.get("MYRM_CHROME_E2E_PORT", "9333").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 9333


def _count_cdp_targets(cdp_port: int) -> int:
    url = f"http://127.0.0.1:{cdp_port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return -1
    if not isinstance(payload, list):
        return -1
    return sum(
        1
        for item in payload
        if isinstance(item, dict) and item.get("type") == "page"
    )


def _count_wave_bound_leases() -> int:
    state_dir = Path(os.environ.get("MYRM_DEV_STATE_DIR", Path.home() / ".local/state/myrm-dev"))
    state_file = state_dir / "wave-orchestrator.json"
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    leases = payload.get("leases")
    if not isinstance(leases, list):
        return 0
    return sum(
        1
        for lease in leases
        if isinstance(lease, dict)
        and lease.get("status") in {"active", "released", "expired"}
        and lease.get("pageId")
        and lease.get("targetId")
    )


def build_tab_hygiene_report(*, cdp_port: int | None = None) -> TabHygieneReport:
    port = cdp_port if cdp_port is not None else _chrome_port()
    lib_dir = Path(__file__).resolve().parent
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import infra_browser_registry as registry

    cdp_count = _count_cdp_targets(port)
    wave_bound = _count_wave_bound_leases()
    infra_count = len(registry.list_infra_targets())
    ok = cdp_count >= 0
    detail = (
        f"cdp_pages={cdp_count} wave_bound={wave_bound} infra_registry={infra_count}"
    )
    return {
        "cdpOpenTargets": cdp_count,
        "waveBoundLeases": wave_bound,
        "infraRegistryTargets": infra_count,
        "ok": ok,
        "detail": detail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Chrome E2E tab hygiene.")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=_chrome_port())
    args = parser.parse_args()
    if not args.report:
        parser.error("--report is required")
    report = build_tab_hygiene_report(cdp_port=args.cdp_port)
    print(f"CHROME_E2E_TAB_HYGIENE: {report['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
