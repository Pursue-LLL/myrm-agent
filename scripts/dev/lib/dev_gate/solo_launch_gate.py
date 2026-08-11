"""SoloLaunchGate — optional LIVE solo window for maintainer batches (§19.12 W5).

SSOT: ``ifm/profile.yaml`` browser-mcp · ``CHROME_MCP_E2E.md`` Playbook 6.

并行是目标：多个 ``./myrm test`` 同时运行是正常用法；日常 LIVE workload 并行由
``wave_orchestrator/lanes.py`` 的并发上限（SHPOIB cap=4 / shared_hot 共享）控制，
门禁只拒错误 launch（同 run id、FAIL_FAST），不拒并行。

显式 ``E2E_SIGNOFF=1`` 或 ``MYRM_E2E_SOLO_SIGNOFF=1`` 时强制 solo（desktop soak 等）：

- 有其他 LIVE lease 在跑 → 拒绝
- ``:3000`` TCP+HTML probe 不绿 → 拒绝
- browser orchestrator daemon 非 READY → 拒绝

日常 LIVE（无上述标记）仅保留环境健康检查（:3000 + orchestrator READY），不拦截并行。
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SoloLaunchVerdict:
    allowed: bool
    reason: str = ""


def _signoff_mode() -> bool:
    """True when desktop soak or maintainer batch requests solo LIVE window."""
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return True
    return os.environ.get("MYRM_E2E_SOLO_SIGNOFF", "").strip() == "1"


def solo_launch_denial_reason(*, workload: str) -> str | None:
    """Return a fail-closed denial line for LIVE workload, or None when allowed."""
    if workload != "LIVE":
        return None
    if os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1":
        return None

    from runtime_identity import frontend_tcp_html_probe_ok

    probe_ok = False
    for _attempt in range(3):
        if frontend_tcp_html_probe_ok("http://127.0.0.1:3000", timeout_sec=5.0):
            probe_ok = True
            break
        time.sleep(2.0)
    if not probe_ok:
        return (
            "SOLO_LAUNCH_DENIED: :3000 TCP+HTML probe failed after retries; "
            "run ./myrm ready --chrome / ui-heal before LIVE signoff"
        )

    from browser_orchestrator import (
        browser_orchestrator_snapshot,
    )

    snap = browser_orchestrator_snapshot()
    health = str(snap.get("health") or "UNKNOWN")
    if health != "READY":
        return (
            f"SOLO_LAUNCH_DENIED: orchestrator health={health} != READY; "
            "run ensure-browser-orchestrator before LIVE signoff"
        )

    if not _signoff_mode():
        # 日常并行 LIVE：并发由 lanes.py 控制，此处不做 solo 拦截。
        return None

    from e2e_lease_liveness import (
        load_wave_snapshot,
        wave_lease_counts,
    )

    counts = wave_lease_counts(load_wave_snapshot())
    other_live = (
        counts.effective_live_agent_shpoib + counts.effective_live_agent_shared_hot
    )
    if other_live > 0:
        return (
            f"SOLO_LAUNCH_DENIED: signoff requires solo — other LIVE leases={other_live}>0; "
            "wait for peers to finish, do not LAUNCH_FORCE during formal signoff"
        )
    return None


def evaluate_solo_launch(*, workload: str) -> SoloLaunchVerdict:
    reason = solo_launch_denial_reason(workload=workload)
    if reason is None:
        return SoloLaunchVerdict(allowed=True)
    return SoloLaunchVerdict(allowed=False, reason=reason)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "check":
        print("usage: python -m solo_launch_gate check", file=sys.stderr)
        return 2
    workload = os.environ.get("MYRM_E2E_WORKLOAD", "").strip() or "LIVE"
    verdict = evaluate_solo_launch(workload=workload)
    print(f"SOLO_LAUNCH_ALLOWED={'yes' if verdict.allowed else 'no'}")
    if verdict.reason:
        print(f"SOLO_LAUNCH_REASON={verdict.reason}")
    return 0 if verdict.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
