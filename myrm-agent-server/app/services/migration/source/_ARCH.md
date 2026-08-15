# services/migration/source 子包架构

## 架构概述

外部数据迁移的**迁移源处理子域**，聚合 `source_*` 模块：来源发现、SSOT 清单、探针、payload 加载与拆分、迁移 DTO、凭证导入、模型迁移。`__init__.py` 为聚合门面统一 re-export 全部公共符号，`app/services/migration/_ARCH.md` 的「文件清单」以本子包为整体条目引用。

封闭集合策略（wizard 自动发现 5 源 + ZIP upload 2 源）与 probe/loader 变更守门规则由父级 `_ARCH.md` 定义；`tests/architecture/test_migration_source_closure.py` 强制 probe 模块、`supported_source_ids()`、loader 注册三处同步。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合 re-export 全部公共符号，收敛为单入口 | ✅ |
| `source_discovery.py` | 核心 | DiscoveredFile / ExternalSource / DiscoveryResult 数据类 + discover_external_sources 编排入口 | ✅ |
| `source_manifest.py` | SSOT | 迁移来源清单（display name / import map / discover mode / deep-link capability）与 authoritative 判定 | ✅ |
| `source_probes.py` | 核心 | 5 源本地 filesystem probe（hermes/claude/openclaw/codex/pi） | ✅ |
| `source_payload_loader.py` | 核心 | 公共 API：load_source_payload / build_coverage_items / extract_pending_skills / supported_source_ids | ✅ |
| `source_payload_loaders_impl.py` | 核心 | 基础 loaders（hermes/codex/claude/chatgpt/gbrain）+ re-export openclaw/pi | ✅ |
| `source_payload_split.py` | 核心 | payload 拆分为 instruction 与 memory 两路（build_instruction_plan / extract_memory_payload） | ✅ |
| `source_migration_types.py` | 核心 | 四车道迁移 DTO（MigrationLanePreview / SourceInstructionPlan / MigrationWizardOptions 等） | ✅ |
| `source_secrets_importer.py` | 辅助 | opt-in 从竞品 `.env` 导入 API Key | ✅ |
| `source_model_migrator.py` | 辅助 | 竞品模型配置 → Myrm 模型设置（Hermes auxiliary slots + Smart Routing economy 推断） | ✅ |

## 模块依赖

- `app.services.memory.imports.import_adapters` — 记忆车道 dry-run / confirm
- `app.services.memory.imports.import_sessions` — dry-run 会话 metadata（instruction plan）
- `app.services.memory.operations.crud.import_archive` — 竞品发现 payload 编排入口
- `app.services.config.service` — 凭证车道 opt-in 写入
