"""Solo-gate heals of the dedicated E2E Chrome: CDP page surge and blank-tab orphan budget.

[INPUT]
- `e2e_core.browser_tab_hygiene` CDP targets and port, `chrome_e2e.gates.orphan_budget` (POS: tab budget of the E2E Chrome)
- `e2e_core.lease_liveness` wave leases, `e2e_session_runtime.registry` live sessions (POS: who else is using the shared stack)

[OUTPUT]
- `attach_parallel_leases()` / `signoff_lane_spawn_clear()` / `signoff_gate_cluster_clear()`: whether the signoff gate holds a solo cluster
- `count_cdp_page_targets()`: CDP page targets of the E2E Chrome, `None` when unknown
- `restart_chrome_if_cdp_page_surge()` / `restart_chrome_if_orphan_budget_exceeded()`: heal a tab storm; True when a heal ran and succeeded

[POS]
Dev gate layer only. Acts on the E2E Chrome only while the gate holds a solo cluster; never signals a peer's process.
"""

from __future__ import annotations

import json
from pathlib import Path

from e2e_core.gate_epoch_core import (
    SoloSnapshot,
    emit,
    myrm_cmd,
    read_solo_snapshot,
    run_heal_flocked,
    solo_cluster_clear,
)

SIGNOFF_GATE_CDP_PAGE_CEILING = 8


def attach_parallel_leases() -> int:
    """Match e2e_bootstrap.sh _e2e_parallel_active_leases (wave first, then live sessions)."""
    from e2e_core.lease_liveness import load_wave_snapshot, shared_effective_lease_count

    effective = shared_effective_lease_count(load_wave_snapshot())
    if effective > 0:
        return effective
    from e2e_session_runtime.registry import list_live_e2e_sessions

    return len(list_live_e2e_sessions())


def signoff_lane_spawn_clear(snapshot: SoloSnapshot) -> bool:
    """Step1 gate lane spawn SSOT — align with chrome attach parallel lease accounting."""
    return solo_cluster_clear(snapshot) and attach_parallel_leases() == 0


def signoff_gate_cluster_clear() -> bool:
    return signoff_lane_spawn_clear(read_solo_snapshot())


def count_cdp_page_targets() -> int | None:
    from e2e_core.browser_tab_hygiene import _chrome_port, _count_cdp_targets

    count = _count_cdp_targets(_chrome_port())
    return count if count >= 0 else None


def _chrome_e2e_listener_pids() -> list[str]:
    import subprocess

    from e2e_core.browser_tab_hygiene import _chrome_port

    port = _chrome_port()
    result = subprocess.run(
        ["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _kill_chrome_e2e_browser(*, wait_sec: float = 45.0) -> bool:
    """Terminate dedicated Myrm E2E Chrome (CDP listener) — clears tab storms."""
    import subprocess
    import time

    pids = _chrome_e2e_listener_pids()
    if not pids:
        return False
    for pid in pids:
        subprocess.run(["kill", "-TERM", pid], check=False)
    deadline = time.monotonic() + min(wait_sec, 15.0)
    while time.monotonic() < deadline:
        if not _chrome_e2e_listener_pids():
            return True
        time.sleep(0.5)
    for pid in _chrome_e2e_listener_pids():
        subprocess.run(["kill", "-KILL", pid], check=False)
    time.sleep(1.0)
    return not _chrome_e2e_listener_pids()


def _ensure_chrome_e2e_browser(monorepo_root: Path) -> int:
    import subprocess

    ensure = (
        monorepo_root / "myrm-agent" / "scripts" / "dev" / "ensure-myrm-chrome-e2e.sh"
    )
    if not ensure.is_file():
        return 1
    completed = subprocess.run(
        ["bash", str(ensure)],
        cwd=str(monorepo_root),
        check=False,
    )
    return int(completed.returncode)


def restart_chrome_if_cdp_page_surge(
    monorepo_root: Path,
    *,
    ceiling: int = SIGNOFF_GATE_CDP_PAGE_CEILING,
) -> bool:
    """Solo signoff heal when CDP page targets exceed gate ceiling (Aug4 PASS had ~3)."""
    count = count_cdp_page_targets()
    if count is None or count <= ceiling:
        return False
    emit(
        "GATE_CDP_SURGE_HEAL: "
        f"pages={count} ceiling={ceiling} — kill E2E Chrome + ensure + attach ready"
    )
    if not _kill_chrome_e2e_browser():
        emit("GATE_CDP_SURGE_HEAL_WARN: E2E Chrome listener still up after kill")
    if _ensure_chrome_e2e_browser(monorepo_root) != 0:
        emit("GATE_CDP_SURGE_HEAL_WARN: ensure-myrm-chrome-e2e failed")
        return False
    after = count_cdp_page_targets()
    if after is not None and after > ceiling:
        emit(
            f"GATE_CDP_SURGE_HEAL_WARN: pages={after} still above ceiling={ceiling} after ensure"
        )
    rc = run_heal_flocked(
        myrm_cmd(monorepo_root, "ready", "--attach", "--chrome"),
        wait_sec=180.0,
    )
    if rc == 0:
        emit("GATE_CDP_SURGE_HEAL_OK: attach ready --chrome after CDP surge kill")
        return True
    emit(f"GATE_CDP_SURGE_HEAL_WARN: attach ready rc={rc}")
    return False


def restart_chrome_if_orphan_budget_exceeded(monorepo_root: Path) -> bool:
    """Solo signoff heal when blank tabs exceed orphan budget (TAB-5)."""
    try:
        from chrome_e2e.gates.orphan_budget import evaluate_orphan_budget
    except ImportError:
        return False
    budget = evaluate_orphan_budget()
    if budget.get("ok"):
        return False
    emit(
        "GATE_ORPHAN_BUDGET_HEAL: "
        f"{json.dumps(budget, sort_keys=True)} — restart --chrome (solo; no peer kill)"
    )
    rc = run_heal_flocked(
        myrm_cmd(monorepo_root, "restart", "--chrome"),
        wait_sec=180.0,
    )
    if rc == 0:
        emit("GATE_ORPHAN_BUDGET_HEAL_OK: restart --chrome")
        return True
    emit(f"GATE_ORPHAN_BUDGET_HEAL_WARN: restart rc={rc}")
    return False
