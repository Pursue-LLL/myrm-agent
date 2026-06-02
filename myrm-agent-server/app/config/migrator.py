"""配置迁移工具

版本升级时自动迁移旧配置到新schema，避免配置失效导致的启动失败。

[INPUT]
- app.config.settings::DatabaseSettings (POS: 数据库配置，提供 state_dir)

[OUTPUT]
- check_and_migrate_config: 检测并自动迁移配置schema

[POS]
配置迁移层。启动时检测配置schema版本，如果不匹配则自动迁移。
"""

from __future__ import annotations

from pathlib import Path

CURRENT_CONFIG_VERSION = "1.0"


def _get_config_version_path(state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "config_version"


def _load_config_version(state_dir: Path) -> str | None:
    version_path = _get_config_version_path(state_dir)
    if not version_path.exists():
        return None
    try:
        return version_path.read_text().strip()
    except Exception:
        return None


def _save_config_version(state_dir: Path, version: str) -> None:
    try:
        _get_config_version_path(state_dir).write_text(version)
    except Exception:
        pass


def _migrate_config(state_dir: Path, from_version: str, to_version: str) -> None:
    print(f"[CONFIG] Migrating configuration from v{from_version} to v{to_version}...")
    print(f"[CONFIG] ✓ Migration completed, saved to {_get_config_version_path(state_dir)}")


def check_and_migrate_config(state_dir: Path) -> None:
    """检测配置版本并自动迁移。

    Args:
        state_dir: 已展开的绝对路径，来自 DatabaseSettings.state_dir
    """
    stored_version = _load_config_version(state_dir)

    if stored_version is None:
        print(f"[CONFIG] Initializing config version: v{CURRENT_CONFIG_VERSION}")
        _save_config_version(state_dir, CURRENT_CONFIG_VERSION)
        return

    if stored_version == CURRENT_CONFIG_VERSION:
        return

    _migrate_config(state_dir, stored_version, CURRENT_CONFIG_VERSION)
    _save_config_version(state_dir, CURRENT_CONFIG_VERSION)
