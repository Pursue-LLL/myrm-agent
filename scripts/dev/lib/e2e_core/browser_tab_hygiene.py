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
# 作为脚本直接执行时（`python .../e2e_core/browser_tab_hygiene.py`），sys.path[0] 指向模块自身所在
# 目录而非 dev lib 根，导致模块级导入 e2e_core.* / dev_gate.* 失败；
# 自举 dev lib 根（当前目录的父目录或向上两级），与 dev_gate/cli.py 保持同模式。
if __package__ in (None, ""):
    _lib_root = str(Path(__file__).resolve().parent.parent)
    if _lib_root not in sys.path:
        sys.path.insert(0, _lib_root)

from e2e_core.real_user_home import real_user_home


class TabHygieneReport(TypedDict):
    cdpOpenTargets: int
    waveBoundLeases: int
    infraRegistryTargets: int
    unboundPages: int
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
        1 for item in payload if isinstance(item, dict) and item.get("type") == "page"
    )


def _count_wave_bound_leases() -> int:
    """Leases bound to an exact session page target (live page ownership count)."""
    return len(_claiming_session_target_ids())


def _claiming_session_target_ids() -> set[str]:
    """Session page targets a live ledger still claims."""
    try:
        from e2e_core.session_page_ledger import protected_session_target_ids
    except ImportError:
        return set()
    return protected_session_target_ids() or set()


def build_tab_hygiene_report(*, cdp_port: int | None = None) -> TabHygieneReport:
    port = cdp_port if cdp_port is not None else _chrome_port()
    lib_dir = Path(__file__).resolve().parent
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import e2e_core.infra_browser_registry as registry

    cdp_count = _count_cdp_targets(port)
    wave_bound = _count_wave_bound_leases()
    infra_count = len(registry.list_infra_targets())
    protected = _protected_target_ids()
    unbound = _count_unbound_pages(port, protected=protected)
    # `ok` must be able to fail and must mean something. An unreadable ledger is
    # not a healthy report (fail-closed), and a page no ledger explains is drift:
    # collapsing `ok` back to `cdp_count >= 0` made a leaked tab indistinguishable
    # from a clean plane, so the doctor's exit code could never flag a leak.
    ok = cdp_count >= 0 and protected is not None and unbound == 0
    detail = (
        f"cdp_pages={cdp_count} wave_bound={wave_bound} "
        f"infra_registry={infra_count} unbound={unbound}"
    )
    return {
        "cdpOpenTargets": cdp_count,
        "waveBoundLeases": wave_bound,
        "infraRegistryTargets": infra_count,
        "unboundPages": unbound,
        "ok": ok,
        "detail": detail,
    }


def _count_unbound_pages(cdp_port: int, *, protected: set[str] | None) -> int:
    """Session-scope pages no ledger claims — the drift a leaked hot-path tab shows up as.

    Ownership is decided by ``browserContextId``, not by URL heuristics: the
    orchestrator always runs a test session inside a dedicated (non-default)
    BrowserContext, while the Agent-Owned Surface and infra warm-ups live in
    Chrome's default context and legitimately have no session ledger. Counting a
    default-context page as unbound would flag a healthy idle plane as drifting.
    """
    if protected is None:
        return -1
    return sum(
        1
        for page in _list_cdp_pages(cdp_port)
        if _is_session_scoped_page(page)
        and isinstance(page.get("id"), str)
        and page["id"].strip() not in protected
    )


def _list_cdp_pages(cdp_port: int) -> list[dict[str, object]]:
    url = f"http://127.0.0.1:{cdp_port}/json/list"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [
        item
        for item in payload
        if isinstance(item, dict) and item.get("type") == "page"
    ]


def _protected_target_ids() -> set[str] | None:
    """Return protected target ids, or None when any live ledger is unreadable.

    Protection covers every lane that legitimately holds a page a wave ledger
    cannot name: session-owned pages from the page-ownership ledger, infra
    warm-ups, the Agent-Owned Surface anchor, and unexpired warm shells (a hot
    shell is still reachable by the hot path, so closing it mid-session would
    be a real regression rather than hygiene).
    """
    protected: set[str] = set()
    state_dir = Path(
        os.environ.get("MYRM_DEV_STATE_DIR", real_user_home() / ".local/state/myrm-dev")
    )
    lib_dir = Path(__file__).resolve().parent
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))

    from e2e_core.session_page_ledger import protected_session_target_ids

    session_targets = protected_session_target_ids()
    if session_targets is None:
        return None
    protected |= session_targets

    import e2e_core.infra_browser_registry as registry

    try:
        for item in registry.list_infra_targets():
            protected.add(item["targetId"])
    except OSError:
        return None
    # The Agent-Owned Surface anchor is a legitimate long-lived page that no
    # wave or infra ledger records. Counting it as unbound would report drift on
    # a healthy, idle plane (and could target it for pruning), so treat a
    # registered anchor as claimed. A missing ledger means no anchor exists —
    # that is a real absence, not an unverifiable one, so it stays fail-open.
    try:
        anchor_payload = json.loads(
            (state_dir / "chrome-e2e-agent-window.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        anchor_payload = {}
    if isinstance(anchor_payload, dict):
        anchor = anchor_payload.get("anchorTargetId")
        if isinstance(anchor, str) and anchor.strip():
            protected.add(anchor.strip())
    protected |= _unexpired_warm_shell_target_ids()
    return protected


def _unexpired_warm_shell_target_ids() -> set[str]:
    """Warm-shell targets still inside their seal TTL (unreachable ⇒ collectable)."""
    try:
        from e2e_core.warm_shell_reap import live_sealed_target_ids
    except ImportError:
        return set()
    return live_sealed_target_ids()


def _is_session_scoped_page(page: dict[str, object]) -> bool:
    """True for orchestrator test-session pages (dedicated non-default context)."""
    context_id = page.get("browserContextId")
    return isinstance(context_id, str) and bool(context_id.strip())


def _is_blankish_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    normalized = url.strip().lower()
    return normalized in {"about:blank", "chrome://newtab/", "chrome://newtab"}


def prune_orphan_cdp_pages(
    *, cdp_port: int | None = None, threshold: int = 20
) -> tuple[int, int]:
    """Reclaim genuinely forgotten session pages; fail-closed when ownership is unknown.

    Two sweeps run, both exact-targetId only:

    1. Dead-session pages — the owner process is gone and its wave lease lapsed.
       These are precisely the leak the old code could never see, because it only
       ever looked at ``about:blank`` pages. A session page (navigated to the real
       UI) therefore stayed alive forever, and its own context was the only thing
       that ever reclaimed it.
    2. Self-owned leftovers — blank pages this very process registered. The
       opt-in ``MYRM_BROWSER_ORCHESTRATOR_PRUNE`` switch and the ``threshold``
       bound belong to this conservative sweep, which is the only one safe to
       gate on "the plane looks small enough to be idle".
    """
    protected = _protected_target_ids()
    if protected is None:
        return 0, 0
    closed = 0
    failed = 0

    dead_closed, dead_failed = _prune_dead_session_pages(cdp_port=cdp_port)
    closed += dead_closed
    failed += dead_failed

    opt_in_closed, opt_in_failed = _prune_self_owned_blanks(
        cdp_port=cdp_port, threshold=threshold
    )
    closed += opt_in_closed
    failed += opt_in_failed
    return closed, failed


def _prune_dead_session_pages(*, cdp_port: int) -> tuple[int, int]:
    from e2e_core.session_page_ledger import prune_dead_session_pages

    return prune_dead_session_pages(cdp_port=cdp_port)


def _prune_self_owned_blanks(*, cdp_port: int, threshold: int) -> tuple[int, int]:
    """Close blank pages this process registered itself (conservative opt-in)."""
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR_PRUNE", "").strip() != "1":
        return 0, 0
    protected = _protected_target_ids()
    if protected is None:
        return 0, 0
    lib_dir = Path(__file__).resolve().parent
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    import e2e_core.infra_browser_registry as registry

    from dev_gate.owner_identity import capture_owner_process_start

    self_pid = os.getpid()
    self_start = capture_owner_process_start(self_pid)
    self_owned = {
        item["targetId"]
        for item in registry.list_infra_targets()
        if item["ownerPid"] == self_pid
        and (
            not item.get("ownerProcessStart")
            or item.get("ownerProcessStart") == self_start
        )
    }
    pages = _list_cdp_pages(cdp_port)
    closed = 0
    failed = 0

    def _close_if_self_blank(page: dict[str, object]) -> None:
        nonlocal closed, failed
        target_id = page.get("id")
        if not isinstance(target_id, str) or not target_id.strip():
            return
        if target_id in protected:
            return
        if target_id not in self_owned:
            return
        if registry.close_exact_target(cdp_port, target_id):
            closed += 1
        else:
            failed += 1

    for page in pages:
        if _is_blankish_url(page.get("url")):
            _close_if_self_blank(page)

    remaining = _list_cdp_pages(cdp_port)
    if len(remaining) > threshold:
        for page in remaining:
            if _is_blankish_url(page.get("url")):
                _close_if_self_blank(page)

    return closed, failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Report Chrome E2E tab hygiene.")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--prune-orphans", action="store_true")
    parser.add_argument("--threshold", type=int, default=20)
    parser.add_argument("--cdp-port", type=int, default=_chrome_port())
    args = parser.parse_args()
    if args.prune_orphans:
        closed, failed = prune_orphan_cdp_pages(
            cdp_port=args.cdp_port, threshold=args.threshold
        )
        print(f"MYRM_CHROME_ORPHAN_PRUNE_OK: closed={closed} failed={failed}")
        return 0 if failed == 0 else 1
    if not args.report:
        parser.error("--report or --prune-orphans is required")
    report = build_tab_hygiene_report(cdp_port=args.cdp_port)
    print(f"CHROME_E2E_TAB_HYGIENE: {report['detail']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
