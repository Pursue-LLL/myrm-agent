"""Reap excess wave leases when holder pytest processes are gone (R58 hygiene).

[INPUT]
- stack_mutation_policy.wave_active_lease_count (POS: active wave lease tally)
- subprocess ps scan for live chrome_e2e pytest parents

[OUTPUT]
- maybe_reap_excess_wave_leases: run wave reap when leases exceed live tests + slack

[POS]
Admission queue relief — stale leases inflate cap pressure under parallel chrome_e2e.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def _monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _count_live_chrome_e2e_pytest() -> int:
    proc = subprocess.run(
        ["ps", "-eo", "pid=,command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return 0
    seen: set[str] = set()
    for line in proc.stdout.splitlines():
        if " -m pytest" not in line:
            continue
        if "tests/e2e/" not in line and "chrome_e2e" not in line:
            continue
        parts = line.strip().split(maxsplit=1)
        if len(parts) < 2:
            continue
        command = parts[1]
        match = re.search(r"(tests/e2e/[^\s]+\.py)", command)
        if match is None:
            continue
        path = match.group(1)
        marker = "chrome_e2e"
        try:
            argv = shlex.split(command)
        except ValueError:
            argv = command.split()
        for idx, token in enumerate(argv):
            if token == "-m" and idx + 1 < len(argv) and "chrome_e2e" in argv[idx + 1]:
                marker = argv[idx + 1]
                break
        key = f"{path}:{marker}"
        if key not in seen:
            seen.add(key)
    return len(seen)


def maybe_reap_excess_wave_leases(*, slack: int = 2) -> bool:
    """Return True when an extra wave reap was triggered."""
    root = _monorepo_root()
    sys.path.insert(0, str(root / "myrm-agent" / "scripts" / "dev" / "lib"))
    from stack_mutation_policy import wave_active_lease_count

    active_leases = wave_active_lease_count(root)
    active_tests = _count_live_chrome_e2e_pytest()
    threshold = active_tests + max(0, int(slack))
    if active_leases <= threshold:
        return False
    wave_bin = root / "myrm-agent" / "scripts" / "dev" / "wave.sh"
    print(
        f"E2E_STALE_LEASE_REAP: wave_leases={active_leases} "
        f"active_tests={active_tests} threshold={threshold} "
        "(do not stop other pytest)",
        file=sys.stderr,
        flush=True,
    )
    env = os.environ.copy()
    subprocess.run(
        ["bash", str(wave_bin), "reap"],
        check=False,
        env=env,
    )
    return True
