"""Fail-closed lease validation immediately before pytest subprocess spawn.

[INPUT]
- tests.support.e2e_runtime_guard::require_e2e_runtime_lease (POS: pytest fixture SSOT)

[OUTPUT]
- CLI exit 0 when MYRM_E2E_LEASE_ID is active and matches agent/lane/runtime
- exit 1 with E2E_LEASE_PYTEST_GATE_FAILED on stderr otherwise

[POS]
Dev Gate pre-pytest gate invoked from scripts/dev/test.sh after runtime sync.
Closes the race where parallel wave reap invalidates a lease between sync and pytest.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _server_root() -> Path:
    override = os.environ.get("MYRM_AGENT_SERVER_ROOT", "").strip()
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2] / "myrm-agent-server"


def main() -> int:
    server_root = _server_root()
    if not server_root.is_dir():
        print(
            f"E2E_LEASE_PYTEST_GATE_FAILED: server root missing at {server_root}",
            file=sys.stderr,
        )
        return 1
    server_root_str = str(server_root)
    if server_root_str not in sys.path:
        sys.path.insert(0, server_root_str)
    from tests.support.e2e_runtime_guard import require_e2e_runtime_lease

    try:
        require_e2e_runtime_lease()
    except RuntimeError as exc:
        print(f"E2E_LEASE_PYTEST_GATE_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
