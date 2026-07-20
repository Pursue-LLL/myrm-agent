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


def _list_cdp_pages(cdp_port: int) -> list[dict[str, object]]:
    url = f"http://127.0.0.1:{cdp_port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict) and item.get("type") == "page"]


def _protected_target_ids() -> set[str]:
    protected: set[str] = set()
    state_dir = Path(os.environ.get("MYRM_DEV_STATE_DIR", Path.home() / ".local/state/myrm-dev"))
    state_file = state_dir / "wave-orchestrator.json"
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    leases = payload.get("leases")
    if isinstance(leases, list):
        for lease in leases:
            if not isinstance(lease, dict):
                continue
            if lease.get("status") not in {"active", "released", "expired"}:
                continue
            target_id = lease.get("targetId")
            if isinstance(target_id, str) and target_id.strip():
                protected.add(target_id.strip())
    lib_dir = Path(__file__).resolve().parent
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import infra_browser_registry as registry

    for item in registry.list_infra_targets():
        protected.add(item["targetId"])
    return protected


def _is_blankish_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    normalized = url.strip().lower()
    return normalized in {"about:blank", "chrome://newtab/", "chrome://newtab"}


def prune_orphan_cdp_pages(*, cdp_port: int | None = None, threshold: int = 20) -> tuple[int, int]:
    """Close unbound blank tabs; when above threshold, close all unbound blankish pages."""
    port = cdp_port if cdp_port is not None else _chrome_port()
    lib_dir = Path(__file__).resolve().parent
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import infra_browser_registry as registry

    protected = _protected_target_ids()
    pages = _list_cdp_pages(port)
    closed = 0
    failed = 0

    def _close_if_unbound(page: dict[str, object]) -> None:
        nonlocal closed, failed
        target_id = page.get("id")
        if not isinstance(target_id, str) or not target_id.strip():
            return
        if target_id in protected:
            return
        if registry.close_exact_target(port, target_id):
            closed += 1
        else:
            failed += 1

    for page in pages:
        if _is_blankish_url(page.get("url")):
            _close_if_unbound(page)

    remaining = _list_cdp_pages(port)
    if len(remaining) > threshold:
        for page in remaining:
            if _is_blankish_url(page.get("url")):
                _close_if_unbound(page)

    return closed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Chrome E2E tab hygiene.")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--prune-orphans", action="store_true")
    parser.add_argument("--threshold", type=int, default=20)
    parser.add_argument("--cdp-port", type=int, default=_chrome_port())
    args = parser.parse_args()
    if args.prune_orphans:
        closed, failed = prune_orphan_cdp_pages(cdp_port=args.cdp_port, threshold=args.threshold)
        print(f"MYRM_CHROME_ORPHAN_PRUNE_OK: closed={closed} failed={failed}")
        return 0 if failed == 0 else 1
    if not args.report:
        parser.error("--report or --prune-orphans is required")
    report = build_tab_hygiene_report(cdp_port=args.cdp_port)
    print(f"CHROME_E2E_TAB_HYGIENE: {report['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
