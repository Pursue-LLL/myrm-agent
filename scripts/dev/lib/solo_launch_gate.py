"""SoloLaunchGate — LIVE workload must launch solo (§19.12 W5 · §23.4 W5 #17).

A LIVE workload (``workload="LIVE"``) is the acceptance window for a real-user
chat: it must never run while parallel chrome_e2e lanes monopolize the browser
plane. This gate fail-closes when:

- effective wave leases > 1 (another lane holds the pool), or
- ``:3000`` TCP+HTML probe is not green, or
- the browser orchestrator daemon is not READY.

The exact contract is the four-term §19.12.2 chain — PreflightContract → this
gate → MuxChatBody → PytestEvidenceSeal → LLMReceipt. Host CPU/memory pressure
is intentionally *not* an admission term: the governor only shrinks operation
credits (it never kills a running private backend), and a local dev machine
running the IDE itself routinely sits above any load floor, which would make
the solo signoff window permanently unavailable.

Non-LIVE workloads (READ/RESOURCE_WRITE/…, i.e. ``workload != "LIVE"``) are not
intercepted — parallel lanes keep their normal launch gate semantics.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SoloLaunchVerdict:
    allowed: bool
    reason: str = ""


def solo_launch_denial_reason(*, workload: str) -> str | None:
    """Return a fail-closed denial line for LIVE workload, or None when allowed."""
    if workload != "LIVE":
        return None
    if os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1":
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
            f"SOLO_LAUNCH_DENIED: other LIVE leases={other_live}>0; "
            "LIVE must launch solo — QUEUE with progress; do not LAUNCH_FORCE "
            "as a default (run ./myrm test -m chrome_e2e solo after peers finish)"
        )

    from runtime_identity import frontend_tcp_html_probe_ok

    if not frontend_tcp_html_probe_ok("http://127.0.0.1:3000", timeout_sec=5.0):
        return (
            "SOLO_LAUNCH_DENIED: :3000 TCP+HTML probe failed; "
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
