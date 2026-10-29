# backup/

## 架构概述

全资产快照存档的三个环节：导出（五类内容打成带校验和的存档并默认脱敏凭据）、增量（只保留相对基线清单发生变化的项）、恢复（导入前体检，再回填目标存储）。三个类都是纯 Python，数据库表、智能体配置、自定义技能、定时任务、记忆五类内容以「名称 → 字符串」的映射传入传出。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出导出器、增量引擎、恢复向导及其清单 / 报告类型 | ✅ |
| `full_stack_snapshot_exporter.py` | 核心 | `FullStackSnapshotExporter.export_snapshot`：生成 `BackupArchiveBundle`（`BackupManifest` 含备份标识、应用版本、整包校验和与逐项文件哈希）；`scrub_credentials` 默认开启，键名含 `api_key` / `token` / `secret` / `password` 等的值替换为 `***REDACTED***` | ✅ |
| `incremental_backup_engine.py` | 核心 | `IncrementalBackupEngine.compute_incremental_diff`：把当前全量快照与基线清单逐项比对 SHA-256 指纹，只收录新增与修改项，并记录父级基线的备份标识；`IncrementalDiffSummary` 统计新增、修改与未变化数量 | ✅ |
| `disaster_recovery_wizard.py` | 核心 | `DisasterRecoveryWizard`：`preflight_validate` 重算校验和与逐文件哈希并比对应用版本（主版本高于当前系统则拒绝，次版本不同只警告）；`restore` 体检不过则拒绝，dry-run 只统计数量，真实恢复先快照目标存储，写入抛错时按快照还原 | ✅ |

## 边界

- 恢复向导复用导出器定义的存档类型，导出器不依赖另外两个模块。
- 存档只做校验和，不做加密。

## 测试

- `tests/unit/core/backup/test_full_stack_backup_and_recovery.py` — 存档与校验和、凭据脱敏（含关闭脱敏保留原值）、增量差异与体积缩减；体检通过、被篡改的存档与主版本不兼容的存档被拒；dry-run 与恢复写入
