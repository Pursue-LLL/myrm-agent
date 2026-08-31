"""Build ordered chrome_e2e marathon queue (STANDARD → LIVE → DESKTOP)."""

from __future__ import annotations

import sys
from pathlib import Path

_WORKLOAD_ORDER = ("STANDARD", "LIVE", "DESKTOP")
_SERVER_PREFIX = "myrm-agent/myrm-agent-server/"


def _to_monorepo_node_id(node_id: str) -> str:
    stripped = node_id.strip()
    if stripped.startswith(_SERVER_PREFIX):
        return stripped
    if stripped.startswith("tests/"):
        return f"{_SERVER_PREFIX}{stripped}"
    return stripped


def build_marathon_queue(monorepo_root: Path) -> tuple[str, ...]:
    scripts_dev = monorepo_root / "scripts" / "dev"
    scripts_dev_str = str(scripts_dev)
    if scripts_dev_str not in sys.path:
        sys.path.insert(0, scripts_dev_str)

    from e2e_session.lane import _collect_node_ids
    from e2e_session.profile import _profiles_from_file, _server_e2e_root

    server_root = _server_e2e_root()
    collected = _collect_node_ids(server_root, ["-m", "chrome_e2e", "-q"])
    if not collected:
        collected = _collect_node_ids(
            server_root, ["-m", "chrome_e2e", "-q"], timeout_sec=180
        )

    buckets: dict[str, list[str]] = {key: [] for key in _WORKLOAD_ORDER}
    for node_id in collected:
        if "::" not in node_id:
            continue
        file_part, test_name = node_id.split("::", 1)
        test_name = test_name.split("[", 1)[0]
        rel = file_part
        if rel.startswith(_SERVER_PREFIX):
            rel = rel[len(_SERVER_PREFIX):]
        path = server_root / rel
        if not path.is_file():
            continue
        profiles = _profiles_from_file(path, test_name=test_name)
        if not profiles:
            continue
        profile = profiles[0]
        workload = profile.workload
        if workload not in buckets:
            buckets[workload] = []
        buckets[workload].append(_to_monorepo_node_id(node_id))

    ordered: list[str] = []
    for workload in _WORKLOAD_ORDER:
        ordered.extend(sorted(set(buckets.get(workload, []))))
    if not ordered:
        raise RuntimeError("CHROME_E2E_MARATHON_EMPTY: no chrome_e2e nodes resolved")
    return tuple(ordered)
