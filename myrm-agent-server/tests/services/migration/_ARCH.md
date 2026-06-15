# tests/services/migration 模块架构

---

## 架构概述

外部助手数据迁移业务层回归测试。覆盖四源 discover/load/split、e2e dry-run、instruction rollback、skills binding。与 `tests/architecture/test_migration_source_closure.py` 互补：本目录测行为，architecture 测 probe/loader 封闭集合同步。

上级：`app/services/migration/_ARCH.md`（Wizard 封闭 4 源政策）。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_source_discovery.py` | 核心 | 四源 filesystem discover（confidence、多源共存、edge cases） |
| `test_source_payload_loader.py` | 核心 | load_source_payload / build_coverage_items |
| `test_source_payload_split.py` | 核心 | instruction vs memory 车道拆分 |
| `test_migration_source_coverage.py` | 核心 | import source 映射、auto 路由回归、supported_source_ids |
| `test_migration_e2e.py` | 核心 | discover → dry-run 端到端（hermes/openclaw） |
| `test_loaders_openclaw_extended.py` | 辅助 | OpenClaw 多 workspace / sessions loader 分支 |
| `test_loader_utils.py` | 辅助 | `_loader_utils` 共享函数 |
| `test_source_secrets_importer.py` | 辅助 | opt-in API key 导入 |
| `test_import_archive_dry_run.py` | 辅助 | import archive dry-run 编排 |
| `test_lane_previews.py` | 辅助 | 四车道 preview DTO |
| `test_instruction_rollback.py` | 辅助 | 指令车道回滚 |
| `test_skill_binding.py` | 辅助 | 技能审核后 agent 绑定 |

---

## 依赖关系

- `app.services.migration.*`
- `app.services.memory.import_adapters`
- `tests/architecture/test_migration_source_closure.py` — 结构闭包（非本目录）

---

## 运行

```bash
uv run pytest tests/services/migration/ -q
```
