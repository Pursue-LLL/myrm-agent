"""配置变更追踪

启动时检测配置变更，输出变更摘要，让用户明确知道新配置已生效。

[INPUT]
- app.config.settings::DatabaseSettings (POS: 数据库配置，提供 state_dir)

[OUTPUT]
- track_config_changes: 追踪配置变更并输出摘要

[POS]
配置变更追踪层。启动时读取上次配置的哈希值，与当前配置哈希比较，输出变更摘要。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _compute_config_hash(config_dict: dict[str, object]) -> str:
    config_json = json.dumps(config_dict, sort_keys=True)
    return hashlib.sha256(config_json.encode()).hexdigest()[:16]


def _get_config_hash_path(state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "config_hash"


def _get_config_snapshot_path(state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "config_snapshot.json"


def _load_previous_hash(state_dir: Path) -> str | None:
    hash_path = _get_config_hash_path(state_dir)
    if not hash_path.exists():
        return None
    try:
        return hash_path.read_text().strip()
    except Exception:
        return None


def _load_previous_config(state_dir: Path) -> dict[str, object] | None:
    snapshot_path = _get_config_snapshot_path(state_dir)
    if not snapshot_path.exists():
        return None
    try:
        raw = json.loads(snapshot_path.read_text())
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return {str(k): v for k, v in raw.items()}


def _save_current_hash(state_dir: Path, config_hash: str) -> None:
    try:
        _get_config_hash_path(state_dir).write_text(config_hash)
    except Exception:
        pass


def _save_config_snapshot(state_dir: Path, config_dict: dict[str, object]) -> None:
    try:
        _get_config_snapshot_path(state_dir).write_text(json.dumps(config_dict, indent=2))
    except Exception:
        pass


def _compute_config_diff(old_config: dict[str, object], new_config: dict[str, object]) -> list[str]:
    changes: list[str] = []
    for key, new_value in new_config.items():
        if key not in old_config:
            changes.append(f"+ {key}: {new_value}")
        elif old_config[key] != new_value:
            changes.append(f"  {key}: {old_config[key]} → {new_value}")
    for key in old_config:
        if key not in new_config:
            changes.append(f"- {key}: {old_config[key]}")
    return changes


def track_config_changes(state_dir: Path, config_dict: dict[str, object]) -> None:
    """追踪配置变更并输出摘要。

    Args:
        state_dir: 已展开的绝对路径，来自 DatabaseSettings.state_dir
        config_dict: 当前配置字典
    """
    current_hash = _compute_config_hash(config_dict)
    previous_hash = _load_previous_hash(state_dir)
    previous_config = _load_previous_config(state_dir)

    if previous_hash is None:
        print("[CONFIG] First run detected")
        _save_current_hash(state_dir, current_hash)
        _save_config_snapshot(state_dir, config_dict)
        return

    if current_hash == previous_hash:
        print("[CONFIG] No configuration changes since last run")
        return

    print("[CONFIG] Configuration changed since last run:")
    if previous_config:
        changes = _compute_config_diff(previous_config, config_dict)
        for change in changes[:10]:
            print(f"[CONFIG] {change}")
        if len(changes) > 10:
            print(f"[CONFIG] ... and {len(changes) - 10} more changes")
    else:
        print("[CONFIG] (Detailed diff unavailable, previous config not found)")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[CONFIG] Changes applied successfully at {timestamp}")

    _save_current_hash(state_dir, current_hash)
    _save_config_snapshot(state_dir, config_dict)
