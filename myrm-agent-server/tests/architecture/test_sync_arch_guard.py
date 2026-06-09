"""Architecture test: sync_arch_file_tables must not rewrite curated _ARCH.md."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent.parent / "scripts" / "sync_arch_file_tables.py"
)
_spec = importlib.util.spec_from_file_location("sync_arch_file_tables", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_needs_refresh = _mod._needs_refresh


@pytest.mark.architecture
def test_sync_skips_mixed_stub_and_completed_iop() -> None:
    content = """# app/lifecycle 模块架构

应用生命周期编排层。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `system.py` | 核心 | Channel Gateway | ⚠️ 待补 |
| `schedulers.py` | 核心 | Cron 启动 | ✅ |
"""
    assert _needs_refresh(content, force=False) is False


@pytest.mark.architecture
def test_sync_refreshes_fully_stub_table() -> None:
    content = """# tasks/

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `metrics.py` | 辅助 | 任务指标 | ⚠️ 待补 |
"""
    assert _needs_refresh(content, force=False) is True
