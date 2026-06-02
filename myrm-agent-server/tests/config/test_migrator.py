"""配置迁移工具测试

覆盖场景:
- M1: 首次运行 - 初始化版本文件
- M2: 版本匹配 - 无需迁移
- M3: 版本不匹配 - 执行迁移
- M4: state_dir 不存在时自动创建
- M5: 版本文件损坏时返回 None（触发首次运行逻辑）
"""

from pathlib import Path

from app.config.migrator import (
    CURRENT_CONFIG_VERSION,
    _get_config_version_path,
    _load_config_version,
    _save_config_version,
    check_and_migrate_config,
)


class TestConfigVersionPath:
    def test_creates_state_dir_if_missing(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "nonexistent" / "nested"
        path = _get_config_version_path(state_dir)
        assert state_dir.exists()
        assert path == state_dir / "config_version"

    def test_returns_config_version_path(self, tmp_path: Path) -> None:
        path = _get_config_version_path(tmp_path)
        assert path == tmp_path / "config_version"


class TestLoadSaveConfigVersion:
    def test_load_returns_none_when_no_file(self, tmp_path: Path) -> None:
        assert _load_config_version(tmp_path) is None

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        _save_config_version(tmp_path, "2.0")
        assert _load_config_version(tmp_path) == "2.0"

    def test_load_strips_whitespace(self, tmp_path: Path) -> None:
        version_path = tmp_path / "config_version"
        version_path.write_text("  1.5\n  ")
        assert _load_config_version(tmp_path) == "1.5"

    def test_load_returns_none_on_corrupt_file(self, tmp_path: Path) -> None:
        version_path = tmp_path / "config_version"
        version_path.mkdir()
        assert _load_config_version(tmp_path) is None


class TestCheckAndMigrateConfig:
    def test_first_run_creates_version_file(self, tmp_path: Path, capsys) -> None:
        check_and_migrate_config(tmp_path)

        assert _load_config_version(tmp_path) == CURRENT_CONFIG_VERSION
        captured = capsys.readouterr()
        assert "Initializing config version" in captured.out

    def test_matching_version_skips_migration(self, tmp_path: Path, capsys) -> None:
        _save_config_version(tmp_path, CURRENT_CONFIG_VERSION)

        check_and_migrate_config(tmp_path)

        captured = capsys.readouterr()
        assert captured.out == ""

    def test_version_mismatch_triggers_migration(self, tmp_path: Path, capsys) -> None:
        _save_config_version(tmp_path, "0.1")

        check_and_migrate_config(tmp_path)

        assert _load_config_version(tmp_path) == CURRENT_CONFIG_VERSION
        captured = capsys.readouterr()
        assert "Migrating" in captured.out
        assert "0.1" in captured.out
        assert CURRENT_CONFIG_VERSION in captured.out

    def test_uses_provided_state_dir_not_home(self, tmp_path: Path) -> None:
        """Verify state_dir parameter is respected (not hardcoded to home)."""
        custom_dir = tmp_path / "custom_sandbox"
        check_and_migrate_config(custom_dir)

        assert (custom_dir / "config_version").exists()
        assert _load_config_version(custom_dir) == CURRENT_CONFIG_VERSION
