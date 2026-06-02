"""配置变更追踪测试

覆盖场景:
- CT1: 首次运行 - 保存哈希和快照
- CT2: 配置未变更 - 输出 "No changes"
- CT3: 配置变更 - 输出 diff 摘要
- CT4: state_dir 不存在时自动创建
- CT5: 哈希计算确定性
- CT6: Diff 计算（新增、修改、删除）
- CT7: 使用 state_dir 参数而非 home 目录
"""

import json
from pathlib import Path

from app.config.change_tracker import (
    _compute_config_diff,
    _compute_config_hash,
    _get_config_hash_path,
    _get_config_snapshot_path,
    _load_previous_config,
    _load_previous_hash,
    _save_config_snapshot,
    _save_current_hash,
    track_config_changes,
)


class TestConfigHash:
    def test_deterministic(self) -> None:
        config = {"key": "value", "num": 42}
        assert _compute_config_hash(config) == _compute_config_hash(config)

    def test_order_independent(self) -> None:
        h1 = _compute_config_hash({"a": 1, "b": 2})
        h2 = _compute_config_hash({"b": 2, "a": 1})
        assert h1 == h2

    def test_different_configs_different_hashes(self) -> None:
        h1 = _compute_config_hash({"a": 1})
        h2 = _compute_config_hash({"a": 2})
        assert h1 != h2

    def test_hash_length_is_16(self) -> None:
        h = _compute_config_hash({"x": "y"})
        assert len(h) == 16


class TestHashPersistence:
    def test_creates_dir_if_missing(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "deep" / "nested"
        path = _get_config_hash_path(state_dir)
        assert state_dir.exists()
        assert path == state_dir / "config_hash"

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        _save_current_hash(tmp_path, "abc123")
        assert _load_previous_hash(tmp_path) == "abc123"

    def test_load_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert _load_previous_hash(tmp_path) is None


class TestSnapshotPersistence:
    def test_creates_dir_if_missing(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "snap" / "dir"
        path = _get_config_snapshot_path(state_dir)
        assert state_dir.exists()
        assert path == state_dir / "config_snapshot.json"

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        config: dict[str, object] = {"port": 8080, "debug": True}
        _save_config_snapshot(tmp_path, config)
        loaded = _load_previous_config(tmp_path)
        assert loaded == config

    def test_load_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert _load_previous_config(tmp_path) is None

    def test_load_returns_none_on_invalid_json(self, tmp_path: Path) -> None:
        (tmp_path / "config_snapshot.json").write_text("not json")
        assert _load_previous_config(tmp_path) is None

    def test_load_returns_none_on_non_dict(self, tmp_path: Path) -> None:
        (tmp_path / "config_snapshot.json").write_text(json.dumps([1, 2, 3]))
        assert _load_previous_config(tmp_path) is None


class TestConfigDiff:
    def test_detects_new_keys(self) -> None:
        diff = _compute_config_diff({}, {"new_key": "val"})
        assert any("+ new_key" in d for d in diff)

    def test_detects_changed_values(self) -> None:
        diff = _compute_config_diff({"key": "old"}, {"key": "new"})
        assert any("old" in d and "new" in d for d in diff)

    def test_detects_removed_keys(self) -> None:
        diff = _compute_config_diff({"gone": "val"}, {})
        assert any("- gone" in d for d in diff)

    def test_no_diff_for_identical(self) -> None:
        diff = _compute_config_diff({"a": 1}, {"a": 1})
        assert diff == []


class TestTrackConfigChanges:
    def test_first_run_saves_hash_and_snapshot(self, tmp_path: Path, capsys) -> None:
        config: dict[str, object] = {"port": 8080}
        track_config_changes(tmp_path, config)

        assert _load_previous_hash(tmp_path) is not None
        assert _load_previous_config(tmp_path) == config
        assert "First run" in capsys.readouterr().out

    def test_no_change_detected(self, tmp_path: Path, capsys) -> None:
        config: dict[str, object] = {"port": 8080}
        track_config_changes(tmp_path, config)
        capsys.readouterr()

        track_config_changes(tmp_path, config)
        assert "No configuration changes" in capsys.readouterr().out

    def test_change_detected_with_diff(self, tmp_path: Path, capsys) -> None:
        track_config_changes(tmp_path, {"port": 8080})
        capsys.readouterr()

        track_config_changes(tmp_path, {"port": 9090})
        out = capsys.readouterr().out
        assert "Configuration changed" in out
        assert "8080" in out
        assert "9090" in out

    def test_uses_provided_state_dir_not_home(self, tmp_path: Path) -> None:
        """Verify state_dir parameter is respected (not hardcoded to home)."""
        custom_dir = tmp_path / "custom"
        track_config_changes(custom_dir, {"x": 1})

        assert (custom_dir / "config_hash").exists()
        assert (custom_dir / "config_snapshot.json").exists()
