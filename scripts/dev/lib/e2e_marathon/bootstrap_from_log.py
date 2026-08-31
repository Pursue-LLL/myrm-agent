"""Bootstrap marathon ledger from legacy stdfirst-resume log."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

from e2e_marathon.ledger import MarathonLedger
from e2e_marathon.paths import resolve_paths

_PASS_RE = re.compile(r"^E2E_STDFIRST_PASS i=R\d+ node=(.+)$")
_FAIL_RE = re.compile(r"^E2E_STDFIRST_FAIL i=R\d+ rc=(\d+) node=(.+)$")
_SKIP_RE = re.compile(r"^E2E_STDFIRST_SKIP i=R\d+ rc=(\d+) node=(.+)$")


def _parse_log(log_path: Path) -> dict[str, tuple[str, int | None]]:
    outcomes: dict[str, tuple[str, int | None]] = {}
    if not log_path.is_file():
        return outcomes
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _PASS_RE.match(line.strip())
        if m:
            outcomes[m.group(1)] = ("PASS", 0)
            continue
        m = _SKIP_RE.match(line.strip())
        if m:
            outcomes[m.group(2)] = ("SKIP", int(m.group(1)))
            continue
        m = _FAIL_RE.match(line.strip())
        if m:
            rc = int(m.group(1))
            node = m.group(2)
            # Legacy script mislabeled rc=0 skips as FAIL
            if rc == 0:
                outcomes[node] = ("SKIP", 0)
            else:
                outcomes[node] = ("FAIL", rc)
    return outcomes


def main() -> int:
    paths = resolve_paths()
    log_path = Path.home() / ".local/state/myrm-dev/e2e-detach/stdfirst-resume-nohup.out"
    if len(sys.argv) > 1:
        log_path = Path(sys.argv[1])
    reset = "--reset" in sys.argv
    queue = MarathonLedger.load(paths.ledger_file)
    if queue is None or not queue.queue or reset:
        from e2e_marathon.manifest import build_marathon_queue

        ledger = MarathonLedger.create(build_marathon_queue(paths.monorepo_root))
    else:
        ledger = queue
        if reset:
            now = time.time()
            for node_id in ledger.queue:
                record = ledger.nodes.get(node_id)
                if record is None:
                    continue
                ledger.nodes[node_id] = type(record)(
                    node_id=record.node_id,
                    index=record.index,
                    outcome="PENDING",
                    rc=None,
                    log_path=None,
                    updated_at=now,
                )
    parsed = _parse_log(log_path)
    applied = 0
    for node_id, (outcome, rc) in parsed.items():
        if node_id not in ledger.nodes:
            continue
        ledger.set_outcome(node_id, outcome, rc, None)
        applied += 1
    ledger.save(paths.ledger_file)
    summary = ledger.summary()
    print(
        f"MARATHON_BOOTSTRAP_OK applied={applied} total={len(ledger.queue)} "
        f"PASS={summary['PASS']} SKIP={summary['SKIP']} FAIL={summary['FAIL']} "
        f"PENDING={summary['PENDING']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
