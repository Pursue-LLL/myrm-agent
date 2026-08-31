"""Run a single chrome_e2e node via test.sh SSOT."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from e2e_marathon.lock import _read_lock
from e2e_marathon.paths import MarathonPaths


def _safe_slug(node_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", node_id)
    return slug[:72]


def run_node(paths: MarathonPaths, node_id: str, index: int) -> tuple[int, Path]:
    paths.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = paths.log_dir / f"R{index}-{_safe_slug(node_id)}.log"
    if not paths.test_sh.is_file():
        raise RuntimeError(f"MARATHON_FAIL: missing test.sh at {paths.test_sh}")
    env = os.environ.copy()
    lock_payload = _read_lock(paths.lock_file)
    if lock_payload is not None:
        token = str(lock_payload.get("token", "")).strip()
        if token:
            env["MYRM_MARATHON_WORKER_TOKEN"] = token
    with log_path.open("w", encoding="utf-8") as log_file:
        result = subprocess.run(
            ["bash", str(paths.test_sh), "-m", "chrome_e2e", "-q", node_id],
            cwd=str(paths.monorepo_root),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
            env=env,
        )
    return result.returncode, log_path
