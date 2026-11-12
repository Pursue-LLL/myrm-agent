"""Frontend dev-server epoch reader for Chrome MCP E2E.

[INPUT]
- frontend <distDir>/dev-server.lock via frontend-warmup.sh (POS: Frontend compile warmth gate)
- `frontend-warmth.json` in the dev state dir (POS: Frontend compile warmth record)
- `frontend_fingerprint.frontend_source_fingerprint()` (POS: what the dev server reads)

[OUTPUT]
- `read_frontend_epoch()`: `FrontendEpoch` (generation, source_fingerprint, pid, started_at, port, bundler_mode) or `None`; `generation` matches `frontend-warmup.sh` `_frontend_lock_generation`
- `read_frontend_hot_state()`: `(shell_hot, client_hot)` validated by dev-server generation; HMR source edits keep it hot

[POS]
Dev infrastructure. Observes the frontend plane; never mutates it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from e2e_core.epoch_state import read_json_file, state_dir
from e2e_core.frontend_fingerprint import frontend_source_fingerprint
from e2e_core.runtime_types import FrontendEpoch


def _frontend_next_dir(frontend_dir: Path) -> Path:
    from dev_paths import scripts_dev_dir

    dev_dir_str = str(scripts_dev_dir(Path(__file__)))
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import frontend_dist_dir

    return frontend_dist_dir(frontend_dir)


def read_frontend_epoch(frontend_dir: Path | None = None) -> FrontendEpoch | None:
    root = frontend_dir
    if root is None:
        override = os.getenv("MYRM_FRONTEND_DIR", "").strip()
        if override:
            root = Path(override)
        else:
            return None
    next_dir = _frontend_next_dir(root)
    lock_path = next_dir / "dev-server.lock"
    raw = read_json_file(lock_path)
    if raw is None:
        return None
    pid = raw.get("pid")
    if pid is not None and not isinstance(pid, int):
        pid = None
    started_at = raw.get("startedAt")
    if not isinstance(started_at, str):
        started_at = ""
    port = raw.get("port")
    if port is not None and not isinstance(port, int):
        port = None
    bundler_stamp = next_dir / "dev-bundler-mode"
    bundler_mode = ""
    if bundler_stamp.is_file():
        bundler_mode = bundler_stamp.read_text(encoding="utf-8").strip()
    # Must match frontend-warmup.sh _frontend_lock_generation (four colon-separated fields).
    generation = ":".join(
        [
            str(pid) if pid is not None else "",
            started_at,
            str(port) if port is not None else "",
            bundler_mode,
        ]
    )
    if generation == ":::":
        return None
    source_fingerprint = frontend_source_fingerprint(root)
    return {
        "generation": generation,
        "source_fingerprint": source_fingerprint,
        "pid": pid,
        "started_at": started_at,
        "port": port,
        "bundler_mode": bundler_mode,
    }


def read_frontend_hot_state(frontend: FrontendEpoch | None) -> tuple[bool, bool]:
    """Validate warmth by dev-server generation; HMR source edits keep it hot."""
    if frontend is None or frontend["pid"] is None:
        return False, False
    try:
        os.kill(frontend["pid"], 0)
    except ProcessLookupError:
        return False, False
    except PermissionError:
        pass
    except OSError:
        return False, False
    warmth = read_json_file(state_dir() / "frontend-warmth.json")
    if warmth is None:
        return False, False
    # Source edits are served by HMR without replacing the dev server or its
    # hydrated client. Endpoint probes validate current reachability separately.
    current = warmth.get("generation") == frontend["generation"] and bool(
        frontend["source_fingerprint"]
    )
    return current, current and warmth.get("client_hot") is True
